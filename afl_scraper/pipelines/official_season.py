"""Preflight and preparation for cached AFL Official seasons."""

from dataclasses import dataclass
from pathlib import Path

from ..diagnostics import summarize_identifiers
from ..models import Game, PlayerGameStats
from ..rounds import is_grouped_first_finals_label, normalize_round_label
from ..scraper import (
    afl_official_cancelled_fixture,
    load_australian_football_manifest,
    load_australian_football_match,
    load_match_metadata_catalog,
    load_raw_match_data,
    load_season_manifest,
)
from ..scraper.metadata_fallback import resolve_fallback_match_record
from ..scraper.models import (
    AustralianFootballMatchData,
    MatchMetadataCatalog,
    RawMatchData,
    SeasonManifest,
)
from ..scraper.season_identities import collect_match_identities
from ..storage import connection_pool, load_player_source_id_map
from ..transform.match import (
    parse_match_datetime,
    resolve_team,
    resolve_venue,
    transform_match,
)

SOURCE = "afl_official"


@dataclass(frozen=True)
class OfficialSeasonCacheReport:
    """Observed coverage and contents of one official season cache."""

    year: int
    scheduled_fixtures: int
    expected_matches: int
    cached_matches: int
    player_stats: int
    participants: int
    cancelled_match_ids: tuple[int, ...] = ()
    missing_match_ids: tuple[int, ...] = ()
    unexpected_match_ids: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_match_ids and not self.unexpected_match_ids


@dataclass(frozen=True)
class PreparedOfficialMatch:
    """One transformed official match ready for a later persistence step."""

    source_match_id: str
    game: Game
    player_stats: list[PlayerGameStats]


def _cached_match_ids(raw_root: Path) -> set[int]:
    """Return positive numeric match directories containing a cache envelope."""
    if not raw_root.exists():
        return set()

    match_ids = set()
    for path in raw_root.glob("*/match.json"):
        try:
            match_id = int(path.parent.name)
        except ValueError:
            continue
        if match_id > 0 and str(match_id) == path.parent.name:
            match_ids.add(match_id)
    return match_ids


def _match_year(match: RawMatchData) -> int:
    return parse_match_datetime(match.details.date, match.details.time).year


def inspect_official_season_cache(
    year: int,
    *,
    manifest_root: Path = Path("data/raw/afl_official/season"),
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> OfficialSeasonCacheReport:
    """Inspect cached manifest members without browser or database access.

    Manifest-member caches are fully revalidated and any invalid member fails
    closed. Valid caches outside the manifest are considered unexpected only
    when their match date belongs to the requested year; unrelated season
    caches can safely share the same raw-data root.
    """
    manifest = load_season_manifest(year, manifest_root)
    scheduled_ids = set(manifest.match_ids)
    cancelled_ids = {
        match_id
        for match_id in manifest.match_ids
        if afl_official_cancelled_fixture(match_id, year) is not None
    }
    expected_ids = scheduled_ids - cancelled_ids
    available_ids = _cached_match_ids(raw_root)
    missing = expected_ids - available_ids
    missing_ids = tuple(sorted(missing))

    identities = {}
    cached_matches = 0
    player_stats = 0
    for match_id in manifest.match_ids:
        if match_id in cancelled_ids:
            continue
        if match_id in missing:
            continue
        try:
            match = load_raw_match_data(match_id, raw_root)
            collect_match_identities(identities, match, match_id, year)
        except Exception as error:
            raise ValueError(
                f"Invalid AFL Official cache for match {match_id}: {error}"
            ) from error
        cached_matches += 1
        player_stats += len(match.home_team_stats) + len(match.away_team_stats)

    unexpected_ids = []
    for match_id in sorted(available_ids - scheduled_ids):
        try:
            match = load_raw_match_data(match_id, raw_root)
            if _match_year(match) == year:
                unexpected_ids.append(match_id)
        except (OSError, ValueError):
            # A non-member cache cannot be associated with this season when its
            # envelope or date is invalid. It will fail closed when preflighting
            # the manifest that actually names it.
            continue

    return OfficialSeasonCacheReport(
        year=year,
        scheduled_fixtures=manifest.match_count,
        expected_matches=len(expected_ids),
        cached_matches=cached_matches,
        player_stats=player_stats,
        participants=len(identities),
        cancelled_match_ids=tuple(sorted(cancelled_ids)),
        missing_match_ids=missing_ids,
        unexpected_match_ids=tuple(unexpected_ids),
    )


def preflight_official_season_cache(
    year: int,
    *,
    manifest_root: Path = Path("data/raw/afl_official/season"),
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> OfficialSeasonCacheReport:
    """Require exact, valid cache coverage for one official season."""
    report = inspect_official_season_cache(
        year,
        manifest_root=manifest_root,
        raw_root=raw_root,
    )
    problems = []
    if report.missing_match_ids:
        problems.append(
            f"missing {len(report.missing_match_ids)} match caches: "
            f"{summarize_identifiers(map(str, report.missing_match_ids))}"
        )
    if report.unexpected_match_ids:
        problems.append(
            f"unexpected {len(report.unexpected_match_ids)} match caches: "
            f"{summarize_identifiers(map(str, report.unexpected_match_ids))}"
        )
    if problems:
        raise ValueError(
            f"AFL Official season cache preflight failed for {year}; "
            + "; ".join(problems)
        )
    return report


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


def _validate_database_references(conn, prepared: list[PreparedOfficialMatch]) -> None:
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
        raise ValueError("AFL Official season preparation failed; " + "; ".join(errors))


def _australian_football_first_finals(
    year: int, raw_root: Path
) -> list[tuple[int, AustralianFootballMatchData]]:
    manifest = load_australian_football_manifest(year, raw_root)
    match_ids = []
    for round_ in manifest.rounds:
        try:
            stage = normalize_round_label(round_.label)
        except ValueError:
            continue
        if stage in {"QF", "EF"}:
            match_ids.extend(round_.match_ids)
    return [
        (match_id, load_australian_football_match(match_id, raw_root))
        for match_id in match_ids
    ]


def _australian_football_candidate_matches(
    official: RawMatchData,
    historical: AustralianFootballMatchData,
) -> bool:
    official_details = official.details
    historical_details = historical.details
    official_teams = (
        resolve_team(official_details.home_team),
        resolve_team(official_details.away_team),
    )
    historical_teams = (
        resolve_team(historical_details.home_team),
        resolve_team(historical_details.away_team),
    )
    if official_teams not in {
        historical_teams,
        tuple(reversed(historical_teams)),
    }:
        return False
    # AustralianFootball records the end-of-regulation score for at least one
    # extra-time final, so scores are corroborating data rather than identity.
    # Team pair, local date and canonical venue uniquely identify these four
    # first-week finals within each season.
    return parse_match_datetime(
        official_details.date, official_details.time
    ).date() == historical_details.date and resolve_venue(
        official_details.venue, SOURCE
    ) == resolve_venue(historical_details.venue, "australian_football")


def _resolve_grouped_first_final(
    source_match_id: int,
    raw_match: RawMatchData,
    manifest: SeasonManifest,
    afl_tables_catalog: MatchMetadataCatalog,
    australian_football_matches: list[tuple[int, AustralianFootballMatchData]],
) -> str:
    fixture = manifest.fixture_for(source_match_id)
    record = resolve_fallback_match_record(fixture, afl_tables_catalog)
    afl_tables_stage = normalize_round_label(record.round)

    candidates = [
        (match_id, match)
        for match_id, match in australian_football_matches
        if _australian_football_candidate_matches(raw_match, match)
    ]
    if len(candidates) != 1:
        sample = ", ".join(str(match_id) for match_id, _ in candidates[:5]) or "none"
        raise ValueError(
            f"Official match {source_match_id} resolved to {len(candidates)} "
            "AustralianFootball first-finals candidates; "
            f"candidates={sample}"
        )
    australian_football_id, australian_football_match = candidates[0]
    australian_football_stage = normalize_round_label(
        australian_football_match.details.round
    )
    stages = {afl_tables_stage, australian_football_stage}
    if not stages <= {"QF", "EF"} or len(stages) != 1:
        raise ValueError(
            f"Conflicting first-finals classification for official match "
            f"{source_match_id}: AFL Tables {record.source_match_id}="
            f"{afl_tables_stage}, AustralianFootball {australian_football_id}="
            f"{australian_football_stage}"
        )
    return stages.pop()


def _prepare_official_matches(
    conn,
    year: int,
    manifest: SeasonManifest,
    matches: list[tuple[int, RawMatchData]],
    *,
    afl_tables_root: Path = Path("data/raw/afl_tables"),
    australian_football_root: Path = Path("data/raw/australian_football"),
) -> list[PreparedOfficialMatch]:
    source_player_ids = {
        stat.afl_official_id
        for _, match in matches
        for stat in match.home_team_stats + match.away_team_stats
    }
    player_id_map = load_player_source_id_map(conn, SOURCE, year, source_player_ids)

    grouped_matches = [
        item for item in matches if is_grouped_first_finals_label(item[1].details.round)
    ]
    afl_tables_catalog: MatchMetadataCatalog | None = None
    australian_football_matches: list[
        tuple[int, AustralianFootballMatchData]
    ] = []
    if grouped_matches:
        afl_tables_catalog = load_match_metadata_catalog(year, afl_tables_root)
        australian_football_matches = _australian_football_first_finals(
            year, australian_football_root
        )

    prepared = []
    for placeholder_id, (source_match_id, raw_match) in enumerate(matches, start=1):

        def resolve_player_id(stat, _team, _year):
            return player_id_map.get(stat.afl_official_id)

        resolved_match = raw_match
        if is_grouped_first_finals_label(raw_match.details.round):
            assert afl_tables_catalog is not None
            stage = _resolve_grouped_first_final(
                source_match_id,
                raw_match,
                manifest,
                afl_tables_catalog,
                australian_football_matches,
            )
            resolved_match = raw_match.model_copy(
                update={
                    "details": raw_match.details.model_copy(update={"round": stage})
                }
            )

        game, player_stats = transform_match(
            resolved_match,
            match_id=placeholder_id,
            source=SOURCE,
            resolve_player_id=resolve_player_id,
        )
        canonical_ids = [stat.player_id for stat in player_stats]
        if len(canonical_ids) != len(set(canonical_ids)):
            raise ValueError(
                f"Canonical player mapping aliases two participants in "
                f"AFL Official match {source_match_id}"
            )
        prepared.append(PreparedOfficialMatch(str(source_match_id), game, player_stats))

    _validate_database_references(conn, prepared)
    return prepared


def prepare_official_season(
    year: int,
    *,
    manifest_root: Path = Path("data/raw/afl_official/season"),
    raw_root: Path = Path("data/raw/afl_official/match"),
    afl_tables_root: Path = Path("data/raw/afl_tables"),
    australian_football_root: Path = Path("data/raw/australian_football"),
) -> list[PreparedOfficialMatch]:
    """Transform a complete official season after read-only preflight.

    Every manifest cache is loaded before the database is opened. The database
    phase performs mapping and reference lookups only; persistence belongs to a
    later pipeline feature.
    """
    report = preflight_official_season_cache(
        year,
        manifest_root=manifest_root,
        raw_root=raw_root,
    )
    manifest = load_season_manifest(year, manifest_root)
    cancelled_ids = set(report.cancelled_match_ids)
    matches = [
        (match_id, load_raw_match_data(match_id, raw_root))
        for match_id in manifest.match_ids
        if match_id not in cancelled_ids
    ]

    with connection_pool() as conn:
        return _prepare_official_matches(
            conn,
            year,
            manifest,
            matches,
            afl_tables_root=afl_tables_root,
            australian_football_root=australian_football_root,
        )


def preflight_official_season(
    conn,
    year: int,
    *,
    manifest_root: Path = Path("data/raw/afl_official/season"),
    raw_root: Path = Path("data/raw/afl_official/match"),
    afl_tables_root: Path = Path("data/raw/afl_tables"),
    australian_football_root: Path = Path("data/raw/australian_football"),
) -> list[PreparedOfficialMatch]:
    """Prepare a complete cached official season using an existing connection."""
    report = preflight_official_season_cache(
        year,
        manifest_root=manifest_root,
        raw_root=raw_root,
    )
    manifest = load_season_manifest(year, manifest_root)
    cancelled_ids = set(report.cancelled_match_ids)
    matches = [
        (match_id, load_raw_match_data(match_id, raw_root))
        for match_id in manifest.match_ids
        if match_id not in cancelled_ids
    ]
    return _prepare_official_matches(
        conn,
        year,
        manifest,
        matches,
        afl_tables_root=afl_tables_root,
        australian_football_root=australian_football_root,
    )
