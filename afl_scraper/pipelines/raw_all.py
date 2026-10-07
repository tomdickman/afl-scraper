"""Database-free, resumable extraction for every configured season."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from ..models import PlayerInfo
from ..scraper import (
    cache_australian_football_season_matches,
    discover_australian_football_season,
    discover_official_season,
    load_australian_football_manifest,
    load_australian_football_match,
    load_raw_match_data,
    load_season_manifest,
    save_australian_football_manifest,
    save_player_ids_to_json,
    save_season_manifest,
    scrape_season_player_ids,
    sync_browser_context,
)
from ..scraper.constants import (
    MAX_CONFIGURED_YEAR,
    MIN_HISTORY_YEAR,
    OFFICIAL_FIXTURE_MIN_YEAR,
)
from ..scraper.models.australian_football import MAX_SUPPORTED_YEAR
from ..transform.australian_football import historical_match_datetime
from ..transform.match import parse_match_datetime, resolve_team, resolve_venue
from ..utils.identity import normalize_person_name
from .historical_players import prepare_player_raw_data


CATALOG_ROOT = Path("data/raw/catalog")


@dataclass(frozen=True)
class RawSeasonReport:
    year: int
    source: str
    matches: int
    player_stats: int
    participants: int
    teams: int
    venues: int
    catalog_path: str


@dataclass(frozen=True)
class RawScrapeReport:
    start_year: int
    end_year: int
    seasons: tuple[RawSeasonReport, ...]
    afl_tables_players: int
    downloaded_profiles: int
    reused_profiles: int

    @property
    def matches(self) -> int:
        return sum(season.matches for season in self.seasons)

    @property
    def player_stats(self) -> int:
        return sum(season.player_stats for season in self.seasons)


def _atomic_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _catalog_path(year: int) -> Path:
    return CATALOG_ROOT / f"{year}.json"


def _historical_players(year: int, matches) -> list[PlayerInfo]:
    players: dict[str, PlayerInfo] = {}
    names: dict[str, str] = {}
    for match_id, match in matches:
        for team, stats in (
            (match.details.home_team, match.home_team_stats),
            (match.details.away_team, match.away_team_stats),
        ):
            for stat in stats:
                normalized = normalize_person_name(stat.player_name)
                previous = names.setdefault(stat.source_player_id, normalized)
                if previous != normalized:
                    raise ValueError(
                        "Conflicting AustralianFootball identity "
                        f"{stat.source_player_id} in match {match_id}: "
                        f"{previous!r} vs {normalized!r}"
                    )
                parts = stat.player_name.split(maxsplit=1)
                if len(parts) != 2:
                    raise ValueError(
                        f"Incomplete AustralianFootball player name "
                        f"{stat.player_name!r} in match {match_id}"
                    )
                players[stat.source_player_id] = PlayerInfo(
                    id=stat.source_player_id,
                    first_name=parts[0],
                    last_name=parts[1],
                    team=team,
                    year=year,
                )
    return sorted(players.values(), key=lambda player: int(player.id))


def _write_historical_catalog(year: int, manifest) -> RawSeasonReport:
    matches = [
        (match_id, load_australian_football_match(match_id))
        for match_id in manifest.match_ids
    ]
    teams = {}
    venues = {}
    player_stats = 0
    for match_id, match in matches:
        if match.details.date.year != year:
            raise ValueError(
                f"AustralianFootball match {match_id} belongs to "
                f"{match.details.date.year}, expected {year}"
            )
        for raw_team in (match.details.home_team, match.details.away_team):
            teams[raw_team] = resolve_team(raw_team)
        raw_venue = match.details.venue
        canonical_venue = resolve_venue(raw_venue, "australian_football")
        historical_match_datetime(match, canonical_venue)
        venues[raw_venue] = canonical_venue
        player_stats += len(match.home_team_stats) + len(match.away_team_stats)

    players = _historical_players(year, matches)
    save_player_ids_to_json(players, "australian_football", year)
    path = _catalog_path(year)
    _atomic_json(
        path,
        {
            "year": year,
            "source": "australian_football",
            "matches": manifest.match_count,
            "player_stats": player_stats,
            "participants": len(players),
            "teams": [
                {"source_name": raw, "canonical_id": canonical}
                for raw, canonical in sorted(teams.items())
            ],
            "venues": [
                {"source_name": raw, "canonical_id": canonical}
                for raw, canonical in sorted(venues.items())
            ],
        },
    )
    return RawSeasonReport(
        year,
        "australian_football",
        manifest.match_count,
        player_stats,
        len(players),
        len(teams),
        len(venues),
        str(path),
    )


def _write_official_catalog(year: int, manifest, players) -> RawSeasonReport:
    teams = {}
    venues = {}
    player_stats = 0
    for match_id in manifest.match_ids:
        match = load_raw_match_data(match_id)
        for raw_team in (match.details.home_team, match.details.away_team):
            teams[raw_team] = resolve_team(raw_team)
        venues[match.details.venue] = resolve_venue(match.details.venue, "afl_official")
        observed_year = parse_match_datetime(
            match.details.date, match.details.time
        ).year
        if observed_year != year:
            raise ValueError(
                f"AFL Official match {match_id} belongs to {observed_year}, "
                f"expected {year}"
            )
        player_stats += len(match.home_team_stats) + len(match.away_team_stats)

    save_player_ids_to_json(players, "afl_official", year)
    path = _catalog_path(year)
    _atomic_json(
        path,
        {
            "year": year,
            "source": "afl_official",
            "matches": manifest.match_count,
            "player_stats": player_stats,
            "participants": len(players),
            "teams": [
                {"source_name": raw, "canonical_id": canonical}
                for raw, canonical in sorted(teams.items())
            ],
            "venues": [
                {"source_name": raw, "canonical_id": canonical}
                for raw, canonical in sorted(venues.items())
            ],
        },
    )
    return RawSeasonReport(
        year,
        "afl_official",
        manifest.match_count,
        player_stats,
        len(players),
        len(teams),
        len(venues),
        str(path),
    )


def scrape_all_raw_data(
    start_year: int = MIN_HISTORY_YEAR,
    end_year: int = MAX_CONFIGURED_YEAR,
    *,
    refresh: bool = False,
    headless: bool = False,
    delay_ms: int = 500,
    progress=None,
) -> RawScrapeReport:
    """Scrape all configured raw sources without opening a database connection."""
    if start_year > end_year:
        raise ValueError("Raw scrape start year must not exceed end year")
    if start_year < MIN_HISTORY_YEAR or end_year > MAX_CONFIGURED_YEAR:
        raise ValueError(
            f"Raw scrape supports {MIN_HISTORY_YEAR}-{MAX_CONFIGURED_YEAR}; "
            f"got {start_year}-{end_year}"
        )
    if delay_ms < 0:
        raise ValueError("Request delay must not be negative")

    def emit(message):
        if progress is not None:
            progress(message)

    emit(f"[{start_year}-{end_year}] validating AFL Tables snapshots and profiles")
    player_report = prepare_player_raw_data(
        start_year,
        end_year,
        refresh=refresh,
        headless=headless,
        delay_ms=delay_ms,
        progress=progress,
    )

    season_reports = []
    with sync_browser_context(headless) as browser:
        for year in range(start_year, end_year + 1):
            emit(f"[{year}] preparing complete raw season cache")
            if year <= MAX_SUPPORTED_YEAR:
                if refresh:
                    manifest = discover_australian_football_season(browser, year)
                    save_australian_football_manifest(manifest)
                else:
                    try:
                        manifest = load_australian_football_manifest(year)
                    except FileNotFoundError:
                        manifest = discover_australian_football_season(browser, year)
                        save_australian_football_manifest(manifest)

                def historical_progress(index, total, match_id, cached):
                    if index == 1 or index == total or index % 10 == 0:
                        emit(
                            f"[{year}] [{index}/{total}] match {match_id} "
                            f"({'cache' if cached else 'live'})"
                        )

                cache_australian_football_season_matches(
                    browser,
                    manifest,
                    refresh=refresh,
                    delay_ms=delay_ms,
                    progress=historical_progress,
                )
                season_reports.append(_write_historical_catalog(year, manifest))
                continue

            if year < OFFICIAL_FIXTURE_MIN_YEAR:
                raise ValueError(f"No match source configured for {year}")
            if refresh:
                manifest = discover_official_season(browser, year)
                save_season_manifest(manifest)
            else:
                try:
                    manifest = load_season_manifest(year)
                except FileNotFoundError:
                    manifest = discover_official_season(browser, year)
                    save_season_manifest(manifest)

            def official_progress(index, total, match_id, cached):
                if index == 1 or index == total or index % 10 == 0:
                    emit(
                        f"[{year}] [{index}/{total}] match {match_id} "
                        f"({'cache' if cached else 'live'})"
                    )

            players = scrape_season_player_ids(
                browser,
                manifest,
                refresh=refresh,
                progress=official_progress,
            )
            season_reports.append(_write_official_catalog(year, manifest, players))

    report = RawScrapeReport(
        start_year,
        end_year,
        tuple(season_reports),
        player_report.unique_players,
        player_report.downloaded_profiles,
        player_report.reused_profiles,
    )
    _atomic_json(
        CATALOG_ROOT / f"{start_year}-{end_year}-report.json",
        {
            **asdict(report),
            "matches": report.matches,
            "player_stats": report.player_stats,
        },
    )
    return report
