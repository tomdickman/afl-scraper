"""Validated AFL Tables fallback for unavailable official player statistics."""

import re
import time as time_module
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext

from ..models.player import PlayerInfo
from ..transform.map_players import normalize_team
from ..utils.identity import normalize_person_name
from .constants import competition_rules_for_year
from .models import MatchMetadataRecord, RawMatchData, RawMatchDetails, RawPlayerStat
from .models.match_metadata import MatchMetadataCatalog

_PLAYER_PATH_PATTERN = re.compile(r"/players/[A-Za-z]/[^/]+\.html$")
_JUMPER_PATTERN = re.compile(r"^(?P<number>\d+)")
_OUTAGE_SIGNATURES = ("site is down", "awaiting solutions")
_STAT_FIELDS = {
    "KI": "kicks",
    "MK": "marks",
    "HB": "handballs",
    "DI": "disposals",
    "GL": "goals",
    "BH": "behinds",
    "HO": "hitouts",
    "TK": "tackles",
    "RB": "rebound_50s",
    "IF": "inside_50s",
    "CL": "clearances",
    "CG": "clangers",
    "FF": "free_kicks_for",
    "FA": "free_kicks_against",
    "CP": "contested_possessions",
    "UP": "uncontested_possessions",
    "CM": "contested_marks",
    "MI": "marks_inside_50",
    "1%": "one_percenters",
    "BO": "bounces",
    "GA": "goal_assists",
    "%P": "time_on_ground_percent",
}
_REQUIRED_HEADERS = {"#", "PLAYER", *_STAT_FIELDS}
_SOURCE_REQUIRED_HEADERS = {
    "#",
    "PLAYER",
    "KI",
    "MK",
    "HB",
    "DI",
    "GL",
    "BH",
    "HO",
    "TK",
    "FF",
    "FA",
}
ProgressCallback = Callable[[int, int, str, bool], None]


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _integer(value: str, field: str) -> int:
    normalized = _normalize(value)
    if not normalized:
        return 0
    if not normalized.isdigit():
        raise ValueError(f"Invalid AFL Tables {field}: {value!r}")
    return int(normalized)


def _player_name(value: str) -> str:
    family_name, separator, given_names = _normalize(value).partition(",")
    if not separator or not family_name.strip() or not given_names.strip():
        raise ValueError(f"Incomplete AFL Tables player name {value!r}")
    return f"{given_names.strip()} {family_name.strip()}"


def _names_match(left: str, right: str) -> bool:
    left_parts = normalize_person_name(left).split()
    right_parts = normalize_person_name(right).split()
    if left_parts == right_parts:
        return True
    if len(left_parts) < 2 or len(right_parts) < 2:
        return False
    if left_parts[1:] != right_parts[1:]:
        return False
    shorter, longer = sorted((left_parts[0], right_parts[0]), key=len)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _official_id(
    player_name: str,
    team: str,
    identities: list[PlayerInfo],
) -> str:
    candidates = {
        player.id: player
        for player in identities
        if normalize_team(player.team) == normalize_team(team)
        and _names_match(player.display_name(), player_name)
    }
    if len(candidates) != 1:
        candidate_ids = ", ".join(sorted(candidates)) or "none"
        raise ValueError(
            f"AFL Tables player {player_name!r} for {team} resolved to "
            f"{len(candidates)} official identities; candidates={candidate_ids}"
        )
    return next(iter(candidates))


def _fantasy_points(stats: dict[str, int]) -> int:
    """Calculate AFL Fantasy points from the source's published components."""
    return (
        stats["kicks"] * 3
        + stats["handballs"] * 2
        + stats["marks"] * 3
        + stats["tackles"] * 4
        + stats["hitouts"]
        + stats["goals"] * 6
        + stats["behinds"]
        + stats["free_kicks_for"]
        - stats["free_kicks_against"] * 3
    )


def _parse_player_table(
    table: Tag,
    team: str,
    identities: list[PlayerInfo],
    expected_players: int,
) -> list[RawPlayerStat]:
    header_rows = table.select("thead tr")
    if len(header_rows) < 2:
        raise ValueError("AFL Tables player-stat table has no column header row")
    headers = [
        _normalize(cell.get_text(" ", strip=True)).upper()
        for cell in header_rows[-1].find_all(["th", "td"])
    ]
    missing = sorted(_REQUIRED_HEADERS - set(headers))
    if missing:
        raise ValueError(f"AFL Tables player-stat table is missing fields: {missing}")
    if len(headers) != len(set(headers)):
        raise ValueError("AFL Tables player-stat table has duplicate fields")

    players = []
    for row in table.select("tbody tr"):
        link = row.find("a", href=_PLAYER_PATH_PATTERN)
        if link is None:
            continue
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != len(headers):
            raise ValueError(
                f"AFL Tables player row has {len(cells)} cells for "
                f"{len(headers)} headers"
            )
        values = {
            header: _normalize(cell.get_text(" ", strip=True))
            for header, cell in zip(headers, cells, strict=True)
        }
        name = _player_name(values["PLAYER"])
        jumper = _JUMPER_PATTERN.match(values["#"])
        if jumper is None:
            raise ValueError(f"Invalid AFL Tables jumper number {values['#']!r}")
        stats = {
            field: _integer(values[header], field)
            for header, field in _STAT_FIELDS.items()
        }
        players.append(
            RawPlayerStat(
                afl_official_id=_official_id(name, team, identities),
                player_name=name,
                jumper_number=int(jumper.group("number")),
                fantasy_points=_fantasy_points(stats),
                metres_gained=None,
                **stats,
            )
        )
    if len(players) != expected_players:
        raise ValueError(
            f"AFL Tables {team} table has {len(players)} players; "
            f"expected {expected_players}"
        )
    return players


def parse_afl_tables_player_stats(
    html: str,
    record: MatchMetadataRecord,
    details: RawMatchDetails,
    identities: list[PlayerInfo],
    *,
    expected_players: int,
) -> RawMatchData:
    """Parse one independently identified AFL Tables match into the raw contract."""
    if not html.strip():
        raise ValueError("AFL Tables player-stat page is empty")
    lowered = html.casefold()
    signature = next((item for item in _OUTAGE_SIGNATURES if item in lowered), None)
    if signature:
        raise RuntimeError(
            f"AFL Tables player-stat page contains outage signature {signature!r}"
        )

    soup = BeautifulSoup(html, "html.parser")
    tables: dict[str, Tag] = {}
    for table in soup.find_all("table"):
        heading = table.select_one("thead tr:first-child th")
        if heading is None:
            continue
        heading_text = _normalize(heading.get_text(" ", strip=True))
        suffix = " Match Statistics"
        if suffix not in heading_text:
            continue
        team = heading_text.partition(suffix)[0]
        canonical = normalize_team(team)
        if canonical in tables:
            raise ValueError(f"Duplicate AFL Tables player-stat table for {team}")
        tables[canonical] = table

    home_key = normalize_team(record.home_team)
    away_key = normalize_team(record.away_team)
    if set(tables) != {home_key, away_key}:
        raise ValueError(
            "AFL Tables player-stat teams do not match resolved metadata: "
            f"observed={sorted(tables)}, expected={sorted((home_key, away_key))}"
        )
    home_stats = _parse_player_table(
        tables[home_key], details.home_team, identities, expected_players
    )
    away_stats = _parse_player_table(
        tables[away_key], details.away_team, identities, expected_players
    )
    home_ids = {stat.afl_official_id for stat in home_stats}
    away_ids = {stat.afl_official_id for stat in away_stats}
    if len(home_ids) != expected_players or len(away_ids) != expected_players:
        raise ValueError("AFL Tables player statistics contain duplicate identities")
    if home_ids & away_ids:
        raise ValueError("AFL Tables player statistics contain cross-team identities")
    return RawMatchData(
        details=details,
        home_team_stats=home_stats,
        away_team_stats=away_stats,
    )


def validate_afl_tables_player_stats_html(
    html: str, record: MatchMetadataRecord, *, expected_players: int
) -> int:
    """Validate source-native AFL Tables rows without requiring official IDs."""
    if not html.strip():
        raise ValueError("AFL Tables player-stat page is empty")
    lowered = html.casefold()
    signature = next((item for item in _OUTAGE_SIGNATURES if item in lowered), None)
    if signature:
        raise RuntimeError(
            f"AFL Tables player-stat page contains outage signature {signature!r}"
        )

    soup = BeautifulSoup(html, "html.parser")
    tables = {}
    suffix = " Match Statistics"
    for table in soup.find_all("table"):
        heading = table.select_one("thead tr:first-child th")
        if heading is None:
            continue
        heading_text = _normalize(heading.get_text(" ", strip=True))
        if suffix not in heading_text:
            continue
        source_team = heading_text.partition(suffix)[0]
        canonical_team = normalize_team(source_team)
        if canonical_team in tables:
            raise ValueError(
                f"Duplicate AFL Tables player-stat table for {source_team}"
            )
        tables[canonical_team] = table

    expected_teams = {
        normalize_team(record.home_team),
        normalize_team(record.away_team),
    }
    if set(tables) != expected_teams:
        raise ValueError(
            "AFL Tables player-stat teams do not match resolved metadata: "
            f"observed={sorted(tables)}, expected={sorted(expected_teams)}"
        )

    ids_by_team = {}
    for team in (record.home_team, record.away_team):
        canonical_team = normalize_team(team)
        table = tables[canonical_team]
        header_rows = table.select("thead tr")
        if len(header_rows) < 2:
            raise ValueError("AFL Tables player-stat table has no column header row")
        headers = [
            _normalize(cell.get_text(" ", strip=True)).upper()
            for cell in header_rows[-1].find_all(["th", "td"])
        ]
        missing = sorted(_SOURCE_REQUIRED_HEADERS - set(headers))
        if missing:
            raise ValueError(f"AFL Tables player-stat table is missing fields: {missing}")
        if len(headers) != len(set(headers)):
            raise ValueError("AFL Tables player-stat table has duplicate fields")

        player_ids = []
        for row in table.select("tbody tr"):
            link = row.find("a", href=_PLAYER_PATH_PATTERN)
            if link is None:
                continue
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) != len(headers):
                raise ValueError(
                    f"AFL Tables player row has {len(cells)} cells for "
                    f"{len(headers)} headers"
                )
            values = {
                header: _normalize(cell.get_text(" ", strip=True))
                for header, cell in zip(headers, cells, strict=True)
            }
            _player_name(values["PLAYER"])
            if _JUMPER_PATTERN.match(values["#"]) is None:
                raise ValueError(f"Invalid AFL Tables jumper number {values['#']!r}")
            stats = {
                field: _integer(values[header], field)
                for header, field in _STAT_FIELDS.items()
                if header in values
            }
            if stats["kicks"] + stats["handballs"] != stats["disposals"]:
                raise ValueError("AFL Tables disposals do not equal kicks + handballs")
            player_ids.append(Path(link["href"]).stem)
        if len(player_ids) != expected_players:
            raise ValueError(
                f"AFL Tables {team} table has {len(player_ids)} players; "
                f"expected {expected_players}"
            )
        if len(player_ids) != len(set(player_ids)):
            raise ValueError(f"AFL Tables {team} table contains duplicate player IDs")
        ids_by_team[canonical_team] = set(player_ids)
    if ids_by_team[normalize_team(record.home_team)] & ids_by_team[
        normalize_team(record.away_team)
    ]:
        raise ValueError("AFL Tables player statistics contain cross-team identities")
    return expected_players * 2


def fetch_afl_tables_player_stats(
    browser: BrowserContext,
    record: MatchMetadataRecord,
) -> str:
    """Fetch one exact AFL Tables record after validating its navigation."""
    page = browser.new_page()
    try:
        response = page.goto(record.source_url)
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"AFL Tables match page returned HTTP {status}")
        if page.url.rstrip("/") != record.source_url.rstrip("/"):
            raise RuntimeError(
                f"AFL Tables match page navigated to unexpected URL {page.url!r}"
            )
        return page.content()
    finally:
        page.close()


def save_afl_tables_match_html(
    html: str,
    record: MatchMetadataRecord,
    raw_root: Path = Path("data/raw/afl_tables/match"),
) -> Path:
    """Atomically retain the alternate raw evidence used by a fallback."""
    path = raw_root / record.source_match_id / "match.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".match-{uuid4().hex}.tmp"
    try:
        temporary.write_text(html, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def cache_afl_tables_season_matches(
    browser: BrowserContext,
    catalog: MatchMetadataCatalog,
    *,
    refresh: bool = False,
    delay_ms: int = 500,
    raw_root: Path = Path("data/raw/afl_tables/match"),
    progress: ProgressCallback | None = None,
) -> int:
    """Cache and revalidate every AFL Tables match-stat page in a season."""
    if delay_ms < 0:
        raise ValueError("AFL Tables request delay must not be negative")
    expected_players = competition_rules_for_year(
        catalog.year
    ).participating_players_per_team
    total = len(catalog.matches)
    live_requests = 0
    for index, record in enumerate(catalog.matches, start=1):
        path = raw_root / record.source_match_id / "match.html"
        cached = path.exists() and not refresh
        if cached:
            html = path.read_text(encoding="utf-8")
        else:
            if live_requests:
                time_module.sleep(delay_ms / 1000)
            html = fetch_afl_tables_player_stats(browser, record)
            save_afl_tables_match_html(html, record, raw_root)
            live_requests += 1
        validate_afl_tables_player_stats_html(
            html, record, expected_players=expected_players
        )
        if progress is not None:
            progress(index, total, record.source_match_id, cached)
    return total * expected_players * 2
