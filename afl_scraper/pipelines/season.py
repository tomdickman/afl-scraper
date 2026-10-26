"""Source-neutral preparation, loading, and reconciliation for AFL seasons."""

from dataclasses import dataclass
from typing import Protocol

from ..models import Game, HistoricalReconciliationReport, PlayerGameStats
from ..season_routing import SeasonPlan, season_plan, season_years
from ..storage import (
    admin_connection_pool,
    allocate_game_id,
    save_game_source_identity,
    save_model,
)
from .historical import preflight_historical_season
from .official_season import preflight_official_season


class PreparedMatch(Protocol):
    source_match_id: str
    game: Game
    player_stats: list[PlayerGameStats]


@dataclass(frozen=True)
class SeasonLoadReport:
    year: int
    source: str
    matches: int
    player_stats: int
    dry_run: bool
    inserted_games: int = 0
    updated_games: int = 0
    already_reconciled: bool = False
    reconciliation: HistoricalReconciliationReport | None = None


@dataclass(frozen=True)
class SeasonBackfillReport:
    start_year: int
    end_year: int
    dry_run: bool
    years: tuple[SeasonLoadReport, ...]

    @property
    def matches(self) -> int:
        return sum(report.matches for report in self.years)

    @property
    def player_stats(self) -> int:
        return sum(report.player_stats for report in self.years)


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
    field for field in PlayerGameStats.model_fields if field != "game_id"
)


def preflight_season(conn, year: int) -> tuple[SeasonPlan, list[PreparedMatch]]:
    """Resolve and completely prepare one season without database writes."""
    plan = season_plan(year)
    if plan.match_source == "australian_football":
        prepared = preflight_historical_season(conn, year)
    else:
        prepared = preflight_official_season(conn, year)
    return plan, prepared


def load_prepared_season(
    conn,
    plan: SeasonPlan,
    prepared: list[PreparedMatch],
    *,
    progress=None,
) -> tuple[int, int]:
    """Persist each prepared game and its player rows as one atomic unit."""
    inserted = 0
    updated = 0
    total = len(prepared)
    for index, match in enumerate(prepared, start=1):
        with conn.transaction():
            game_id, is_new_identity = allocate_game_id(
                conn, plan.match_source, match.source_match_id
            )
            game = match.game.model_copy(update={"id": game_id})
            player_stats = [
                stat.model_copy(update={"game_id": game_id})
                for stat in match.player_stats
            ]
            result = save_model(conn, game)
            if is_new_identity:
                save_game_source_identity(
                    conn, plan.match_source, match.source_match_id, game_id
                )
            for stat in player_stats:
                save_model(conn, stat)
        if result.was_inserted:
            inserted += 1
        else:
            updated += 1
        if progress is not None:
            progress(index, total, match.source_match_id, result.was_inserted)
    return inserted, updated


def reconcile_season(
    conn,
    plan: SeasonPlan,
    prepared: list[PreparedMatch],
) -> HistoricalReconciliationReport:
    """Compare every prepared game and player statistic with persisted rows."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT identity.source_match_id, game.id,
                   {', '.join(f'game.{field}' for field in _GAME_FIELDS)}
            FROM game_source_identity AS identity
            JOIN game ON game.id = identity.game_id
            WHERE identity.source = %(source)s AND game.year = %(year)s
            """,
            {"source": plan.match_source, "year": plan.year},
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
            {"source": plan.match_source, "year": plan.year},
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
            if (plan.sparse_player_stats and expected_value is None) or actual[
                field
            ] == expected_value:
                continue
            value_mismatches.append(
                f"stat {identity[0]}:{identity[1]} {field}: "
                f"expected {expected_value!r}, got {actual[field]!r}"
            )

    return HistoricalReconciliationReport(
        year=plan.year,
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


def _require_reconciled(report: HistoricalReconciliationReport) -> None:
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
        f"Database reconciliation failed for {report.year} with "
        f"{report.mismatch_count} differences: {'; '.join(samples)}"
    )


def _report(
    plan: SeasonPlan,
    prepared: list[PreparedMatch],
    *,
    dry_run: bool,
    inserted: int = 0,
    updated: int = 0,
    already_reconciled: bool = False,
    reconciliation: HistoricalReconciliationReport,
) -> SeasonLoadReport:
    return SeasonLoadReport(
        year=plan.year,
        source=plan.match_source,
        matches=len(prepared),
        player_stats=sum(len(match.player_stats) for match in prepared),
        dry_run=dry_run,
        inserted_games=inserted,
        updated_games=updated,
        already_reconciled=already_reconciled,
        reconciliation=reconciliation,
    )


def season_pipeline(
    year: int, *, load: bool = False, progress=None
) -> SeasonLoadReport:
    """Preflight, optionally load, and reconcile one provider-routed season."""
    with admin_connection_pool() as conn:
        plan, prepared = preflight_season(conn, year)
        reconciliation = reconcile_season(conn, plan, prepared)
        if not load:
            return _report(
                plan,
                prepared,
                dry_run=True,
                reconciliation=reconciliation,
            )
        if reconciliation.ok:
            return _report(
                plan,
                prepared,
                dry_run=False,
                already_reconciled=True,
                reconciliation=reconciliation,
            )
        inserted, updated = load_prepared_season(
            conn, plan, prepared, progress=progress
        )
        reconciliation = reconcile_season(conn, plan, prepared)
        _require_reconciled(reconciliation)
        return _report(
            plan,
            prepared,
            dry_run=False,
            inserted=inserted,
            updated=updated,
            reconciliation=reconciliation,
        )


def backfill_pipeline(
    start_year: int,
    end_year: int,
    *,
    load: bool = False,
    progress=None,
) -> SeasonBackfillReport:
    """Preflight a complete range before optionally loading any season."""
    years = season_years(start_year, end_year)
    prepared_by_year = {}
    reports = []
    with admin_connection_pool() as conn:
        for year in years:
            if progress:
                progress(year, "preflighting")
            plan, prepared = preflight_season(conn, year)
            reconciliation = reconcile_season(conn, plan, prepared)
            prepared_by_year[year] = (plan, prepared, reconciliation)

        for year in years:
            plan, prepared, reconciliation = prepared_by_year[year]
            if not load:
                reports.append(
                    _report(
                        plan,
                        prepared,
                        dry_run=True,
                        reconciliation=reconciliation,
                    )
                )
                continue
            if reconciliation.ok:
                reports.append(
                    _report(
                        plan,
                        prepared,
                        dry_run=False,
                        already_reconciled=True,
                        reconciliation=reconciliation,
                    )
                )
                continue
            if progress:
                progress(year, "loading")
            inserted, updated = load_prepared_season(conn, plan, prepared)
            reconciliation = reconcile_season(conn, plan, prepared)
            _require_reconciled(reconciliation)
            reports.append(
                _report(
                    plan,
                    prepared,
                    dry_run=False,
                    inserted=inserted,
                    updated=updated,
                    reconciliation=reconciliation,
                )
            )
    return SeasonBackfillReport(
        start_year=start_year,
        end_year=end_year,
        dry_run=not load,
        years=tuple(reports),
    )
