"""Preflighted, resumable loading of AustralianFootball historical seasons."""

from dataclasses import dataclass

from ..models import (
    Game,
    HistoricalReconciliationReport,
    PlayerGameStats,
    PlayerInfo,
)
from ..scraper import (
    load_australian_football_manifest,
    load_australian_football_match,
)
from ..storage import (
    admin_connection_pool,
    allocate_game_id,
    load_player_source_id_map,
    save_game_source_identity,
    save_model,
)
from ..transform import transform_australian_football_match
from ..utils.identity import normalize_person_name


SOURCE = "australian_football"


@dataclass(frozen=True)
class PreparedHistoricalMatch:
    source_match_id: str
    game: Game
    player_stats: list[PlayerGameStats]


@dataclass(frozen=True)
class HistoricalLoadReport:
    year: int
    matches: int
    player_stats: int
    dry_run: bool
    inserted_games: int = 0
    updated_games: int = 0


def load_historical_match_caches(year: int):
    """Load every manifest member and reject cross-match identity drift."""
    manifest = load_australian_football_manifest(year)
    matches = []
    names: dict[str, str] = {}
    for match_id in manifest.match_ids:
        match = load_australian_football_match(match_id)
        if match.details.date.year != year:
            raise ValueError(
                f"Historical match {match_id} belongs to "
                f"{match.details.date.year}, expected {year}"
            )
        for stat in match.home_team_stats + match.away_team_stats:
            normalized = normalize_person_name(stat.player_name)
            previous = names.setdefault(stat.source_player_id, normalized)
            if previous != normalized:
                raise ValueError(
                    f"Conflicting AustralianFootball identity "
                    f"{stat.source_player_id}: {previous!r} vs {normalized!r}"
                )
        matches.append((match_id, match))
    return manifest, matches


def historical_source_player_ids(year: int) -> set[str]:
    _, matches = load_historical_match_caches(year)
    return {
        stat.source_player_id
        for _, match in matches
        for stat in match.home_team_stats + match.away_team_stats
    }


def historical_source_players(year: int) -> list[PlayerInfo]:
    """Build a deterministic season participant snapshot from validated caches."""
    _, matches = load_historical_match_caches(year)
    players: dict[str, PlayerInfo] = {}
    for _, match in matches:
        team_stats = (
            (match.details.home_team, match.home_team_stats),
            (match.details.away_team, match.away_team_stats),
        )
        for team, stats in team_stats:
            for stat in stats:
                names = stat.player_name.split(maxsplit=1)
                if len(names) != 2:
                    raise ValueError(
                        f"AustralianFootball player {stat.source_player_id} has "
                        f"an incomplete name {stat.player_name!r}"
                    )
                # A player can change clubs during a season. Retaining the last
                # observed club matches the end-of-season roster snapshots used
                # to generate conservative mapping candidates.
                players[stat.source_player_id] = PlayerInfo(
                    id=stat.source_player_id,
                    first_name=names[0],
                    last_name=names[1],
                    team=team,
                    year=year,
                )
    return sorted(players.values(), key=lambda player: int(player.id))


def _existing_ids(conn, table: str, identifiers: set[str]) -> set[str]:
    if not identifiers:
        return set()
    if table not in {"player", "team", "venue"}:
        raise ValueError(f"Unsupported reference table: {table}")
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT id FROM "{table}" WHERE id = ANY(%(identifiers)s)',
            {"identifiers": sorted(identifiers)},
        )
        return {row[0] for row in cur.fetchall()}


def _validate_database_references(
    conn, prepared: list[PreparedHistoricalMatch]
) -> None:
    expected = {
        "player": {stat.player_id for match in prepared for stat in match.player_stats},
        "team": {
            team
            for match in prepared
            for team in (match.game.home_team, match.game.away_team)
        },
        "venue": {match.game.venue for match in prepared},
    }
    errors = []
    for table, identifiers in expected.items():
        missing = sorted(identifiers - _existing_ids(conn, table, identifiers))
        if missing:
            errors.append(f"missing {table} rows: {', '.join(missing)}")
    if errors:
        raise ValueError("Historical preflight failed; " + "; ".join(errors))


def preflight_historical_season(conn, year: int) -> list[PreparedHistoricalMatch]:
    manifest, matches = load_historical_match_caches(year)
    source_player_ids = {
        stat.source_player_id
        for _, match in matches
        for stat in match.home_team_stats + match.away_team_stats
    }
    player_id_map = load_player_source_id_map(conn, SOURCE, year, source_player_ids)

    prepared = []
    for placeholder_id, (source_match_id, raw_match) in enumerate(matches, start=1):
        game, player_stats = transform_australian_football_match(
            raw_match,
            game_id=placeholder_id,
            player_id_map=player_id_map,
        )
        prepared.append(
            PreparedHistoricalMatch(str(source_match_id), game, player_stats)
        )
    if len(prepared) != manifest.match_count:
        raise ValueError(
            f"Prepared {len(prepared)} matches, expected {manifest.match_count}"
        )
    _validate_database_references(conn, prepared)
    return prepared


def load_prepared_historical_season(
    conn,
    year: int,
    prepared: list[PreparedHistoricalMatch],
    *,
    progress=None,
) -> HistoricalLoadReport:
    """Load a preflighted season with one transaction per complete match."""
    inserted = 0
    updated = 0
    total = len(prepared)
    for index, match in enumerate(prepared, start=1):
        with conn.transaction():
            game_id, is_new_identity = allocate_game_id(
                conn, SOURCE, match.source_match_id
            )
            game = match.game.model_copy(update={"id": game_id})
            player_stats = [
                stat.model_copy(update={"game_id": game_id})
                for stat in match.player_stats
            ]
            result = save_model(conn, game)
            if is_new_identity:
                save_game_source_identity(conn, SOURCE, match.source_match_id, game_id)
            for stat in player_stats:
                save_model(conn, stat)
            if result.was_inserted:
                inserted += 1
            else:
                updated += 1
        if progress is not None:
            progress(index, total, match.source_match_id, result.was_inserted)

    return HistoricalLoadReport(
        year,
        len(prepared),
        sum(len(match.player_stats) for match in prepared),
        False,
        inserted_games=inserted,
        updated_games=updated,
    )


_GAME_FIELDS = (
    "venue",
    "start_date",
    "round",
    "home_team",
    "away_team",
    "home_goals",
    "home_behinds",
    "away_goals",
    "away_behinds",
)
_STAT_FIELDS = tuple(
    field for field in PlayerGameStats.model_fields if field not in {"game_id"}
)


def reconcile_historical_season(
    conn, year: int, prepared: list[PreparedHistoricalMatch]
) -> HistoricalReconciliationReport:
    """Compare expected transformed records with source-qualified DB records."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT identity.source_match_id, game.id,
                   {', '.join(f'game.{field}' for field in _GAME_FIELDS)}
            FROM game_source_identity AS identity
            JOIN game ON game.id = identity.game_id
            WHERE identity.source = %(source)s AND game.year = %(year)s
            """,
            {"source": SOURCE, "year": year},
        )
        game_rows = cur.fetchall()

    database_games = {
        str(row[0]): {"id": row[1], **dict(zip(_GAME_FIELDS, row[2:], strict=True))}
        for row in game_rows
    }
    expected_games = {match.source_match_id: match for match in prepared}
    missing_matches = sorted(set(expected_games) - set(database_games))
    unexpected_matches = sorted(set(database_games) - set(expected_games))
    value_mismatches = []
    for source_match_id in sorted(set(expected_games) & set(database_games)):
        expected = expected_games[source_match_id].game
        actual = database_games[source_match_id]
        for field in _GAME_FIELDS:
            expected_value = getattr(expected, field)
            if actual[field] != expected_value:
                value_mismatches.append(
                    f"match {source_match_id} {field}: "
                    f"expected {expected_value!r}, got {actual[field]!r}"
                )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT identity.source_match_id,
                   {', '.join(f'stats.{field}' for field in _STAT_FIELDS)}
            FROM game_source_identity AS identity
            JOIN game ON game.id = identity.game_id
            JOIN player_game_stats AS stats ON stats.game_id = game.id
            WHERE identity.source = %(source)s AND game.year = %(year)s
            """,
            {"source": SOURCE, "year": year},
        )
        stat_rows = cur.fetchall()

    database_stats = {
        (str(row[0]), row[1]): dict(zip(_STAT_FIELDS, row[1:], strict=True))
        for row in stat_rows
    }
    expected_stats = {
        (match.source_match_id, stat.player_id): stat
        for match in prepared
        for stat in match.player_stats
    }
    missing_stats = sorted(
        f"{match_id}:{player_id}"
        for match_id, player_id in set(expected_stats) - set(database_stats)
    )
    unexpected_stats = sorted(
        f"{match_id}:{player_id}"
        for match_id, player_id in set(database_stats) - set(expected_stats)
    )
    for identity in sorted(set(expected_stats) & set(database_stats)):
        expected = expected_stats[identity]
        actual = database_stats[identity]
        for field in _STAT_FIELDS:
            expected_value = getattr(expected, field)
            # Sparse historical rows deliberately preserve richer values.
            if expected_value is not None and actual[field] != expected_value:
                value_mismatches.append(
                    f"stat {identity[0]}:{identity[1]} {field}: "
                    f"expected {expected_value!r}, got {actual[field]!r}"
                )

    return HistoricalReconciliationReport(
        year=year,
        expected_matches=len(expected_games),
        database_matches=len(database_games),
        expected_player_stats=len(expected_stats),
        database_player_stats=len(database_stats),
        missing_match_ids=missing_matches,
        unexpected_match_ids=unexpected_matches,
        missing_player_stats=missing_stats,
        unexpected_player_stats=unexpected_stats,
        value_mismatches=value_mismatches,
    )


def require_reconciled(report: HistoricalReconciliationReport) -> None:
    if report.ok:
        return
    samples = (
        report.missing_match_ids
        + report.unexpected_match_ids
        + report.missing_player_stats
        + report.unexpected_player_stats
        + report.value_mismatches
    )[:10]
    raise ValueError(
        f"Historical database reconciliation failed for {report.year} with "
        f"{report.mismatch_count} differences: {'; '.join(samples)}"
    )


def historical_season_pipeline(year: int, *, load: bool = False):
    """Preflight a complete season, then optionally load each match atomically."""
    with admin_connection_pool() as conn:
        prepared = preflight_historical_season(conn, year)
        stat_count = sum(len(match.player_stats) for match in prepared)
        if not load:
            return HistoricalLoadReport(year, len(prepared), stat_count, True)
        report = load_prepared_historical_season(conn, year, prepared)
        require_reconciled(reconcile_historical_season(conn, year, prepared))
        return report
