"""Preflight and preparation for cached AFL Official seasons."""

from dataclasses import dataclass
from pathlib import Path

from ..diagnostics import summarize_identifiers
from ..models import Game, PlayerGameStats
from ..scraper import load_raw_match_data, load_season_manifest
from ..scraper.models import RawMatchData
from ..scraper.season_identities import collect_match_identities
from ..storage import admin_connection_pool, load_player_source_id_map
from ..transform.match import parse_match_datetime, transform_match


SOURCE = "afl_official"


@dataclass(frozen=True)
class OfficialSeasonCacheReport:
    """Observed coverage and contents of one official season cache."""

    year: int
    expected_matches: int
    cached_matches: int
    player_stats: int
    participants: int
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
    expected_ids = set(manifest.match_ids)
    available_ids = _cached_match_ids(raw_root)
    missing = expected_ids - available_ids
    missing_ids = tuple(sorted(missing))

    identities = {}
    cached_matches = 0
    player_stats = 0
    for match_id in manifest.match_ids:
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
    for match_id in sorted(available_ids - expected_ids):
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
        expected_matches=manifest.match_count,
        cached_matches=cached_matches,
        player_stats=player_stats,
        participants=len(identities),
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


def _prepare_official_matches(
    conn,
    year: int,
    matches: list[tuple[int, RawMatchData]],
) -> list[PreparedOfficialMatch]:
    source_player_ids = {
        stat.afl_official_id
        for _, match in matches
        for stat in match.home_team_stats + match.away_team_stats
    }
    player_id_map = load_player_source_id_map(conn, SOURCE, year, source_player_ids)

    prepared = []
    for placeholder_id, (source_match_id, raw_match) in enumerate(matches, start=1):

        def resolve_player_id(stat, _team, _year):
            return player_id_map.get(stat.afl_official_id)

        game, player_stats = transform_match(
            raw_match,
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
) -> list[PreparedOfficialMatch]:
    """Transform a complete official season after read-only preflight.

    Every manifest cache is loaded before the database is opened. The database
    phase performs mapping and reference lookups only; persistence belongs to a
    later pipeline feature.
    """
    preflight_official_season_cache(
        year,
        manifest_root=manifest_root,
        raw_root=raw_root,
    )
    manifest = load_season_manifest(year, manifest_root)
    matches = [
        (match_id, load_raw_match_data(match_id, raw_root))
        for match_id in manifest.match_ids
    ]

    with admin_connection_pool() as conn:
        return _prepare_official_matches(conn, year, matches)
