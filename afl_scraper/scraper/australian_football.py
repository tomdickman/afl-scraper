"""Fail-closed extraction for AustralianFootball historical match pages."""

import json
import re
import time as time_module
from collections.abc import Callable
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .constants import competition_rules_for_year
from .models import (
    AustralianFootballCancelledFixture,
    AustralianFootballMatchData,
    AustralianFootballMatchDetails,
    AustralianFootballPlayerStat,
    AustralianFootballSeasonManifest,
    AustralianFootballSourceOmission,
    CachedAustralianFootballCancellation,
    CachedAustralianFootballMatch,
    CachedAustralianFootballSourceOmission,
    DiscoveredRound,
)
from .models.australian_football import MAX_AVAILABLE_YEAR, MIN_SUPPORTED_YEAR


BASE_URL = "https://australianfootball.com"
_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "australian_football_match_exceptions.jsonc"
)
_SOURCE_OMISSIONS_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "australian_football_source_omissions.jsonc"
)
MATCH_PATH_PATTERN = re.compile(r"^/game/view/(?P<match_id>\d+)$")
PLAYER_PATH_PATTERN = re.compile(
    r"^/players/player/[^/]+/(?P<player_id>\d+)$", re.IGNORECASE
)
_MATCH_METADATA_PATTERN = re.compile(
    r"^(?:Round:\s*)?(?P<round>.+?)\s+Venue:\s*(?P<venue>.+?)\s+"
    r"Date:\s*(?P<date>[A-Za-z]{3},\s*\d{1,2}-\d{1,2}-\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}\s*[ap]m)\s+Crowd:\s*(?P<crowd>[\d,]+|N/A|-)"
    r"(?:\s*\(\s*Avg\s+(?P<average_crowd>[\d,]+)\s*\))?$",
    re.IGNORECASE,
)
_SCORE_PATTERN = re.compile(r"^(?P<goals>\d+)\.\s*(?P<behinds>\d+)\.\s*(?P<total>\d+)$")
_PLAYER_HEADERS = (
    "#",
    "PLAYER",
    "K",
    "M",
    "H",
    "D",
    "G",
    "B",
    "HO",
    "T",
    "FF",
    "FA",
    "AGE",
    "GAMES",
    "G",
)
_MATCH_FETCH_ATTEMPTS = 3
_MATCH_SUMMARY_WAIT_MS = 10_000

ProgressCallback = Callable[[int, int, int, bool], None]


class _IncompleteMatchPageError(ValueError):
    """The source returned a match shell before its summary was available."""


@cache
def _reviewed_cancelled_fixtures() -> dict[int, AustralianFootballCancelledFixture]:
    content = _CONFIG_PATH.read_text(encoding="utf-8")
    raw = json.loads(re.sub(r"(?m)(^|\s)//.*$", r"\1", content))
    fixtures = {
        int(match_id): AustralianFootballCancelledFixture.model_validate(value)
        for match_id, value in raw.items()
    }
    for match_id, fixture in fixtures.items():
        if fixture.match_id != match_id:
            raise ValueError(
                f"Cancelled fixture key {match_id} contains match {fixture.match_id}"
            )
    official_ids = [
        fixture.afl_official_match_id
        for fixture in fixtures.values()
        if fixture.afl_official_match_id is not None
    ]
    if len(official_ids) != len(set(official_ids)):
        raise ValueError("Cancelled fixtures contain duplicate AFL Official match IDs")
    return fixtures


def australian_football_cancelled_fixture(
    match_id: int | str, year: int
) -> AustralianFootballCancelledFixture | None:
    """Return reviewed cancellation metadata for one source fixture, if any."""
    normalized_match_id = _normalize_match_id(match_id)
    fixture = _reviewed_cancelled_fixtures().get(normalized_match_id)
    if fixture is not None and fixture.year != year:
        raise ValueError(
            f"Cancelled fixture {normalized_match_id} belongs to {fixture.year}, "
            f"expected {year}"
        )
    return fixture


@cache
def _reviewed_source_omissions() -> dict[int, AustralianFootballSourceOmission]:
    content = _SOURCE_OMISSIONS_CONFIG_PATH.read_text(encoding="utf-8")
    raw = json.loads(re.sub(r"(?m)(^|\s)//.*$", r"\1", content))
    omissions = {}
    for year_key, season in raw.items():
        year = int(year_key)
        if season.get("year") != year:
            raise ValueError(
                f"Source omission key {year} contains season {season.get('year')}"
            )
        reason = season.get("reason")
        for match in season.get("matches", []):
            match_id = match.get("match_id")
            omission = AustralianFootballSourceOmission.model_validate(
                {
                    **match,
                    "year": year,
                    "reason": reason,
                    "evidence_urls": [
                        australian_football_match_url(match_id),
                        f"https://www.afl.com.au/afl/matches/"
                        f"{match.get('afl_official_match_id')}",
                        f"https://afltables.com/afl/stats/games/{year}/"
                        f"{match.get('afl_tables_match_id')}.html",
                    ],
                }
            )
            if omission.match_id in omissions:
                raise ValueError(
                    f"Duplicate AustralianFootball source omission "
                    f"{omission.match_id}"
                )
            omissions[omission.match_id] = omission
    official_ids = [item.afl_official_match_id for item in omissions.values()]
    tables_ids = [item.afl_tables_match_id for item in omissions.values()]
    if len(official_ids) != len(set(official_ids)):
        raise ValueError("Source omissions contain duplicate AFL Official match IDs")
    if len(tables_ids) != len(set(tables_ids)):
        raise ValueError("Source omissions contain duplicate AFL Tables match IDs")
    return omissions


def australian_football_source_omission(
    match_id: int | str, year: int
) -> AustralianFootballSourceOmission | None:
    """Return reviewed evidence for a played match missing source data."""
    normalized_match_id = _normalize_match_id(match_id)
    omission = _reviewed_source_omissions().get(normalized_match_id)
    if omission is not None and omission.year != year:
        raise ValueError(
            f"Source omission {normalized_match_id} belongs to {omission.year}, "
            f"expected {year}"
        )
    return omission


def afl_official_cancelled_fixture(
    match_id: int | str, year: int
) -> AustralianFootballCancelledFixture | None:
    """Return reviewed cancellation metadata for one AFL Official fixture."""
    try:
        normalized_match_id = int(match_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid AFL Official match ID: {match_id!r}") from exc
    if normalized_match_id <= 0 or str(match_id).strip() != str(normalized_match_id):
        raise ValueError(f"Invalid AFL Official match ID: {match_id!r}")

    fixture = next(
        (
            item
            for item in _reviewed_cancelled_fixtures().values()
            if item.afl_official_match_id == normalized_match_id
        ),
        None,
    )
    if fixture is not None and fixture.year != year:
        raise ValueError(
            f"Cancelled AFL Official fixture {normalized_match_id} belongs to "
            f"{fixture.year}, expected {year}"
        )
    return fixture


def cancellation_cache_matches_review(
    cached: AustralianFootballCancelledFixture,
    reviewed: AustralianFootballCancelledFixture,
) -> bool:
    """Compare AustralianFootball facts while ignoring cross-source identity."""
    excluded = {"afl_official_match_id"}
    return cached.model_dump(exclude=excluded) == reviewed.model_dump(exclude=excluded)


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _validate_year(year: int) -> None:
    if not MIN_SUPPORTED_YEAR <= year <= MAX_AVAILABLE_YEAR:
        raise ValueError(
            "AustralianFootball source supports "
            f"{MIN_SUPPORTED_YEAR}-{MAX_AVAILABLE_YEAR}; got {year}"
        )
    competition_rules_for_year(year)


def _normalize_match_id(match_id: int | str) -> int:
    try:
        normalized = int(match_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid AustralianFootball match ID: {match_id!r}") from exc
    if normalized <= 0 or str(match_id).strip() != str(normalized):
        raise ValueError(f"Invalid AustralianFootball match ID: {match_id!r}")
    return normalized


def australian_football_season_url(year: int) -> str:
    _validate_year(year)
    # The final path component is an opaque source record ID. It matched the
    # calendar year until AustralianFootball inserted a second 2022 season.
    reviewed_season_id = year + 1 if year >= 2023 else year
    return _australian_football_season_url_for_id(reviewed_season_id)


def _australian_football_season_url_for_id(season_id: int | str) -> str:
    normalized_season_id = str(season_id).strip()
    if not normalized_season_id.isdigit():
        raise ValueError(
            f"Invalid AustralianFootball season ID {normalized_season_id!r}"
        )
    return (
        f"{BASE_URL}/seasons/season/afl/138/"
        f"premiership%2Bseason/1/1/{normalized_season_id}"
    )


def _resolve_australian_football_season_url(html: str, year: int) -> str:
    """Resolve a calendar year through the source's opaque season selector."""
    _validate_year(year)
    soup = BeautifulSoup(html, "html.parser")
    selector = soup.select_one("select#season_select")
    if selector is None:
        raise ValueError("AustralianFootball page has no season selector")
    options = [
        option
        for option in selector.find_all("option")
        if _normalize_text(option.get_text()) == str(year)
    ]
    if len(options) != 1:
        raise ValueError(
            f"Expected one AustralianFootball season selector for {year}, "
            f"found {len(options)}"
        )
    season_id = options[0].get("value", "")
    return _australian_football_season_url_for_id(season_id)


def australian_football_match_url(match_id: int | str) -> str:
    return f"{BASE_URL}/game/view/{_normalize_match_id(match_id)}"


def _round_label(heading: Tag) -> str:
    direct_text = next(
        (
            _normalize_text(str(child))
            for child in heading.children
            if isinstance(child, NavigableString) and _normalize_text(str(child))
        ),
        "",
    )
    label = direct_text or _normalize_text(heading.get_text(" ", strip=True))
    if not label:
        raise ValueError("AustralianFootball season contains a blank round heading")
    return label


def _round_match_ids(heading: Tag) -> list[int]:
    match_ids: list[int] = []
    sibling = heading.next_sibling
    while sibling is not None:
        if isinstance(sibling, Tag) and sibling.name == "h4":
            break
        if isinstance(sibling, Tag):
            for link in sibling.select('a[href*="/game/view/"]'):
                match = MATCH_PATH_PATTERN.fullmatch(link.get("href", ""))
                if match is None:
                    raise ValueError(
                        "Could not parse AustralianFootball match ID from "
                        f"{link.get('href')!r}"
                    )
                match_ids.append(int(match.group("match_id")))
        sibling = sibling.next_sibling
    return list(dict.fromkeys(match_ids))


def parse_australian_football_season(
    html: str,
    year: int,
    *,
    source_url: str | None = None,
    discovered_at: datetime | None = None,
) -> AustralianFootballSeasonManifest:
    """Parse and validate every match link from one historical season page."""
    _validate_year(year)
    if not html.strip():
        raise ValueError("AustralianFootball season page is empty")
    soup = BeautifulSoup(html, "html.parser")

    title = _normalize_text(soup.title.get_text()) if soup.title else ""
    expected_title = f"Season {year}"
    if "AFL Premiership Season" not in title or expected_title not in title:
        raise ValueError(f"Unexpected AustralianFootball season page title {title!r}")
    rounds = []
    for heading in soup.find_all("h4"):
        match_ids = _round_match_ids(heading)
        if match_ids:
            rounds.append(
                DiscoveredRound(label=_round_label(heading), match_ids=match_ids)
            )
    return AustralianFootballSeasonManifest(
        year=year,
        season_url=source_url or australian_football_season_url(year),
        discovered_at=discovered_at or datetime.now(timezone.utc),
        rounds=rounds,
    )


def _parse_non_negative_integer(value: str, field: str) -> int:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"Missing AustralianFootball {field}")
    try:
        result = int(normalized.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Invalid AustralianFootball {field}: {value!r}") from exc
    if result < 0:
        raise ValueError(f"Negative AustralianFootball {field}: {result}")
    return result


def _parse_optional_non_negative_integer(value: str, field: str) -> int | None:
    if not _normalize_text(value):
        return None
    return _parse_non_negative_integer(value, field)


def _parse_match_details(table: Tag) -> AustralianFootballMatchDetails:
    rows = table.find_all("tr")
    if len(rows) != 4:
        raise ValueError(
            f"AustralianFootball match summary has {len(rows)} rows; expected 4"
        )
    metadata = _normalize_text(rows[0].get_text(" ", strip=True))
    match = _MATCH_METADATA_PATTERN.fullmatch(metadata)
    if match is None:
        raise ValueError(f"Could not parse match metadata from {metadata!r}")
    match_datetime = datetime.strptime(
        f"{match.group('date')} {match.group('time')}", "%a, %d-%m-%Y %I:%M %p"
    )

    parsed_teams = []
    for row in rows[1:3]:
        cells = [
            _normalize_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]
        if len(cells) < 3:
            raise ValueError("AustralianFootball score row is incomplete")
        score = next(
            (
                _SCORE_PATTERN.fullmatch(value)
                for value in reversed(cells[1:])
                if _SCORE_PATTERN.fullmatch(value)
            ),
            None,
        )
        if score is None:
            raise ValueError(f"Could not parse final score from {cells!r}")
        parsed_teams.append(
            (
                cells[0],
                int(score.group("goals")),
                int(score.group("behinds")),
                int(score.group("total")),
            )
        )

    crowd_text = match.group("crowd")
    crowd = (
        None
        if crowd_text in {"N/A", "-"}
        else _parse_non_negative_integer(crowd_text, "crowd")
    )
    home, away = parsed_teams
    return AustralianFootballMatchDetails(
        home_team=home[0],
        away_team=away[0],
        round=_normalize_text(match.group("round")),
        date=match_datetime.date(),
        local_time=match_datetime.time(),
        venue=_normalize_text(match.group("venue")),
        crowd=crowd,
        home_team_goals=home[1],
        home_team_behinds=home[2],
        home_team_total=home[3],
        away_team_goals=away[1],
        away_team_behinds=away[2],
        away_team_total=away[3],
    )


def _player_name(value: str) -> str:
    family_name, separator, given_names = _normalize_text(value).partition(",")
    if not separator or not family_name.strip() or not given_names.strip():
        raise ValueError(f"Incomplete AustralianFootball player name {value!r}")
    return f"{given_names.strip()} {family_name.strip()}"


def _parse_player_table(
    table: Tag, expected_team: str, expected_players: int
) -> list[AustralianFootballPlayerStat]:
    header_rows = table.select("thead tr")
    if len(header_rows) != 2:
        raise ValueError("AustralianFootball player table must have two header rows")
    group_headers = [
        _normalize_text(cell.get_text(" ", strip=True))
        for cell in header_rows[0].find_all("th")
    ]
    if len(group_headers) != 3 or group_headers[0] != expected_team:
        raise ValueError(
            f"Player table team {group_headers[:1]!r} does not match {expected_team!r}"
        )
    headers = tuple(
        _normalize_text(cell.get_text(" ", strip=True)).upper()
        for cell in header_rows[1].find_all("th")
    )
    if headers != _PLAYER_HEADERS:
        raise ValueError(
            f"Unexpected AustralianFootball player headers: {list(headers)!r}"
        )

    players = []
    for row in table.select("tbody tr"):
        link = row.select_one('a[href*="/players/player/"]')
        if link is None:
            continue
        href = link.get("href", "")
        player_match = PLAYER_PATH_PATTERN.fullmatch(href)
        if player_match is None:
            raise ValueError(
                f"Could not parse AustralianFootball player ID from {href!r}"
            )
        cells = [
            _normalize_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]
        if len(cells) != len(_PLAYER_HEADERS):
            raise ValueError(
                f"AustralianFootball player row has {len(cells)} cells; "
                f"expected {len(_PLAYER_HEADERS)}"
            )
        values = [
            _parse_non_negative_integer(cells[index], _PLAYER_HEADERS[index])
            for index in range(2, 12)
        ]
        players.append(
            AustralianFootballPlayerStat(
                source_player_id=player_match.group("player_id"),
                player_name=_player_name(cells[1]),
                jumper_number=_parse_optional_non_negative_integer(
                    cells[0], "jumper number"
                ),
                kicks=values[0],
                marks=values[1],
                handballs=values[2],
                disposals=values[3],
                goals=values[4],
                behinds=values[5],
                hitouts=values[6],
                tackles=values[7],
                free_kicks_for=values[8],
                free_kicks_against=values[9],
            )
        )
    if len(players) != expected_players:
        raise ValueError(
            f"AustralianFootball {expected_team} table has {len(players)} players; "
            f"expected {expected_players}"
        )
    return players


def _canonical_source_team(team: str, year: int) -> str:
    aliases = {
        "brisbane": "Brisbane Lions",
        "st. kilda": "St Kilda",
    }
    normalized = _normalize_text(team).casefold()
    # AustralianFootball applies the modern club name retrospectively, while
    # the reviewed competition contract uses the name published in that era.
    if normalized == "north melbourne" and year <= 2007:
        return "Kangaroos"
    return aliases.get(normalized, _normalize_text(team))


def parse_australian_football_match(
    html: str, year: int
) -> AustralianFootballMatchData:
    """Parse one complete historical match without inventing unavailable stats."""
    _validate_year(year)
    if not html.strip():
        raise ValueError("AustralianFootball match page is empty")
    soup = BeautifulSoup(html, "html.parser")
    title = _normalize_text(soup.title.get_text()) if soup.title else ""
    if "Match Details:" not in title:
        raise ValueError(f"Unexpected AustralianFootball match page title {title!r}")

    summary_tables = []
    for table in soup.find_all("table"):
        table_text = _normalize_text(table.get_text(" ", strip=True))
        if all(marker in table_text for marker in ("Venue:", "Date:", "Crowd:")):
            summary_tables.append(table)
    if not summary_tables:
        raise _IncompleteMatchPageError(
            "Expected one AustralianFootball match summary, found 0"
        )
    if len(summary_tables) != 1:
        raise ValueError(
            f"Expected one AustralianFootball match summary, found {len(summary_tables)}"
        )
    details = _parse_match_details(summary_tables[0])
    if details.date.year != year:
        raise ValueError(
            f"AustralianFootball match belongs to {details.date.year}, expected {year}"
        )

    heading = soup.find(["h1", "h2", "h3"], string=re.compile(r"\s+vs\s+"))
    expected_heading = f"{details.home_team} vs {details.away_team}"
    if heading is None or _normalize_text(heading.get_text()) != expected_heading:
        raise ValueError(
            f"AustralianFootball match heading does not equal {expected_heading!r}"
        )

    rules = competition_rules_for_year(year)
    expected_teams = set(rules.teams)
    observed_teams = {
        _canonical_source_team(details.home_team, year),
        _canonical_source_team(details.away_team, year),
    }
    if not observed_teams <= expected_teams:
        raise ValueError(
            f"Unexpected teams for AustralianFootball season {year}: "
            f"{sorted(observed_teams - expected_teams)}"
        )

    player_tables = [
        table
        for table in soup.find_all("table")
        if table.select_one("thead")
        and "Match Stats"
        in _normalize_text(table.select_one("thead").get_text(" ", strip=True))
    ]
    if len(player_tables) != 2:
        raise ValueError(
            f"Expected two AustralianFootball player tables, found {len(player_tables)}"
        )
    home_stats = _parse_player_table(
        player_tables[0], details.home_team, rules.participating_players_per_team
    )
    away_stats = _parse_player_table(
        player_tables[1], details.away_team, rules.participating_players_per_team
    )
    return AustralianFootballMatchData(
        details=details,
        home_team_stats=home_stats,
        away_team_stats=away_stats,
    )


def _validate_navigation(
    page: Page, response, expected_url: str, page_type: str
) -> None:
    if response is None or not response.ok:
        status = response.status if response is not None else "no response"
        mode_hint = (
            "; if using headless mode, retry with a visible browser "
            "(`--no-headless`)"
            if status == 403
            else ""
        )
        raise RuntimeError(
            f"AustralianFootball {page_type} page returned HTTP {status}{mode_hint}"
        )
    if page.url.rstrip("/") != expected_url.rstrip("/"):
        raise RuntimeError(
            f"AustralianFootball {page_type} page navigated to unexpected URL "
            f"{page.url!r}"
        )


def _wait_for_match_summary(page: Page) -> None:
    page.locator("table").filter(has_text="Venue:").first.wait_for(
        state="attached", timeout=_MATCH_SUMMARY_WAIT_MS
    )


def discover_australian_football_season(
    browser: BrowserContext, year: int
) -> AustralianFootballSeasonManifest:
    """Navigate to and validate a configured season index."""
    url = australian_football_season_url(year)
    page = browser.new_page()
    try:
        response = page.goto(url)
        _validate_navigation(page, response, url, "season")
        html = page.content()
        resolved_url = _resolve_australian_football_season_url(html, year)
        if resolved_url != url:
            url = resolved_url
            response = page.goto(url)
            _validate_navigation(page, response, url, "season")
            html = page.content()
        return parse_australian_football_season(html, year, source_url=url)
    finally:
        page.close()


def australian_football_manifest_path(
    year: int,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    _validate_year(year)
    return raw_root / "season" / str(year) / "manifest.json"


def _atomic_write_text(path: Path, content: str, temporary_prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{temporary_prefix}-{uuid4().hex}.tmp"
    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def save_australian_football_manifest(
    manifest: AustralianFootballSeasonManifest,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    """Atomically save a validated source-specific season manifest."""
    path = australian_football_manifest_path(manifest.year, raw_root)
    _atomic_write_text(path, manifest.model_dump_json(indent=2) + "\n", "manifest")
    return path


def load_australian_football_manifest(
    year: int,
    raw_root: Path = Path("data/raw/australian_football"),
) -> AustralianFootballSeasonManifest:
    path = australian_football_manifest_path(year, raw_root)
    if not path.exists():
        raise FileNotFoundError(
            f"Historical season manifest not found: {path}. "
            f"Run `scrape season {year}` first."
        )
    manifest = AustralianFootballSeasonManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if manifest.year != year:
        raise ValueError(
            f"Historical manifest at {path} contains {manifest.year}, expected {year}"
        )
    return manifest


def australian_football_match_cache_path(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    return raw_root / "match" / str(_normalize_match_id(match_id)) / "match.json"


def australian_football_cancellation_cache_path(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    return raw_root / "match" / str(_normalize_match_id(match_id)) / "cancellation.json"


def australian_football_source_omission_cache_path(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    return raw_root / "match" / str(_normalize_match_id(match_id)) / "omission.json"


def save_australian_football_match(
    data: AustralianFootballMatchData,
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    """Atomically save a fully validated historical match cache."""
    normalized_match_id = _normalize_match_id(match_id)
    validated_data = AustralianFootballMatchData.model_validate(data)
    path = australian_football_match_cache_path(normalized_match_id, raw_root)
    envelope = CachedAustralianFootballMatch(
        match_id=normalized_match_id,
        source_url=australian_football_match_url(normalized_match_id),
        scraped_at=datetime.now(timezone.utc),
        data=validated_data,
    )
    _atomic_write_text(path, envelope.model_dump_json(indent=2) + "\n", "match")
    return path


def load_australian_football_match(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> AustralianFootballMatchData:
    normalized_match_id = _normalize_match_id(match_id)
    path = australian_football_match_cache_path(normalized_match_id, raw_root)
    if not path.exists():
        raise FileNotFoundError(f"Historical match cache not found: {path}")
    envelope = CachedAustralianFootballMatch.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if envelope.match_id != normalized_match_id:
        raise ValueError(
            f"Historical cache at {path} contains match {envelope.match_id}, "
            f"expected {normalized_match_id}"
        )
    return envelope.data


def save_australian_football_cancellation(
    fixture: AustralianFootballCancelledFixture,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    """Cache reviewed evidence for a fixture that was never played."""
    path = australian_football_cancellation_cache_path(fixture.match_id, raw_root)
    envelope = CachedAustralianFootballCancellation(
        match_id=fixture.match_id,
        source_url=australian_football_match_url(fixture.match_id),
        recorded_at=datetime.now(timezone.utc),
        data=fixture,
    )
    _atomic_write_text(path, envelope.model_dump_json(indent=2) + "\n", "cancellation")
    return path


def load_australian_football_cancellation(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> AustralianFootballCancelledFixture:
    normalized_match_id = _normalize_match_id(match_id)
    path = australian_football_cancellation_cache_path(normalized_match_id, raw_root)
    if not path.exists():
        raise FileNotFoundError(f"Historical cancellation cache not found: {path}")
    envelope = CachedAustralianFootballCancellation.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if envelope.match_id != normalized_match_id:
        raise ValueError(
            f"Historical cancellation cache at {path} contains match "
            f"{envelope.match_id}, expected {normalized_match_id}"
        )
    return envelope.data


def save_australian_football_source_omission(
    omission: AustralianFootballSourceOmission,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    """Cache reviewed evidence for a played match missing source data."""
    path = australian_football_source_omission_cache_path(omission.match_id, raw_root)
    envelope = CachedAustralianFootballSourceOmission(
        match_id=omission.match_id,
        source_url=australian_football_match_url(omission.match_id),
        recorded_at=datetime.now(timezone.utc),
        data=omission,
    )
    _atomic_write_text(path, envelope.model_dump_json(indent=2) + "\n", "omission")
    return path


def load_australian_football_source_omission(
    match_id: int | str,
    raw_root: Path = Path("data/raw/australian_football"),
) -> AustralianFootballSourceOmission:
    normalized_match_id = _normalize_match_id(match_id)
    path = australian_football_source_omission_cache_path(normalized_match_id, raw_root)
    if not path.exists():
        raise FileNotFoundError(f"Historical source omission cache not found: {path}")
    envelope = CachedAustralianFootballSourceOmission.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if envelope.match_id != normalized_match_id:
        raise ValueError(
            f"Historical source omission cache at {path} contains match "
            f"{envelope.match_id}, expected {normalized_match_id}"
        )
    return envelope.data


def scrape_australian_football_match(
    browser: BrowserContext,
    match_id: int | str,
    year: int,
    raw_root: Path = Path("data/raw/australian_football"),
) -> Path:
    """Navigate, validate, and cache one AustralianFootball historical match."""
    _validate_year(year)
    normalized_match_id = _normalize_match_id(match_id)
    url = australian_football_match_url(normalized_match_id)
    page = browser.new_page()
    try:
        response = page.goto(url)
        _validate_navigation(page, response, url, "match")
        for attempt in range(1, _MATCH_FETCH_ATTEMPTS + 1):
            html = page.content()
            try:
                data = parse_australian_football_match(html, year)
            except _IncompleteMatchPageError as error:
                if attempt == _MATCH_FETCH_ATTEMPTS:
                    raise _IncompleteMatchPageError(
                        f"AustralianFootball match {normalized_match_id} ({url}) "
                        f"still has no match summary after "
                        f"{_MATCH_FETCH_ATTEMPTS} attempts"
                    ) from error
                try:
                    _wait_for_match_summary(page)
                except PlaywrightTimeoutError:
                    response = page.goto(url)
                    _validate_navigation(page, response, url, "match")
                continue
            break
        path = australian_football_match_cache_path(normalized_match_id, raw_root)
        html_path = path.with_name("match.html")
        _atomic_write_text(html_path, html, "match-html")
        return save_australian_football_match(data, normalized_match_id, raw_root)
    finally:
        page.close()


def cache_australian_football_season_matches(
    browser: BrowserContext,
    manifest: AustralianFootballSeasonManifest,
    *,
    refresh: bool = False,
    delay_ms: int = 500,
    progress: ProgressCallback | None = None,
    raw_root: Path = Path("data/raw/australian_football"),
) -> list[Path]:
    """Cache all season matches, resuming only from missing validated caches."""
    if delay_ms < 0:
        raise ValueError("Historical source delay must not be negative")
    paths = []
    total = manifest.match_count
    made_live_request = False
    for index, match_id in enumerate(manifest.match_ids, start=1):
        omission = australian_football_source_omission(match_id, manifest.year)
        if omission is not None:
            cached = False
            if not refresh:
                try:
                    cached_omission = load_australian_football_source_omission(
                        match_id, raw_root
                    )
                except FileNotFoundError:
                    pass
                else:
                    if cached_omission != omission:
                        raise ValueError(
                            f"Historical source omission cache for match {match_id} "
                            "does not match its reviewed configuration"
                        )
                    cached = True
            path = (
                australian_football_source_omission_cache_path(match_id, raw_root)
                if cached
                else save_australian_football_source_omission(omission, raw_root)
            )
            paths.append(path)
            if progress is not None:
                progress(index, total, match_id, cached)
            continue

        cancellation = australian_football_cancelled_fixture(match_id, manifest.year)
        if cancellation is not None:
            cached = False
            cache_needs_upgrade = False
            if not refresh:
                try:
                    cached_cancellation = load_australian_football_cancellation(
                        match_id, raw_root
                    )
                except FileNotFoundError:
                    pass
                else:
                    if not cancellation_cache_matches_review(
                        cached_cancellation, cancellation
                    ):
                        raise ValueError(
                            f"Historical cancellation cache for match {match_id} "
                            "does not match its reviewed configuration"
                        )
                    cached = True
                    cache_needs_upgrade = cached_cancellation != cancellation
            path = (
                save_australian_football_cancellation(cancellation, raw_root)
                if cache_needs_upgrade
                else australian_football_cancellation_cache_path(match_id, raw_root)
                if cached
                else save_australian_football_cancellation(cancellation, raw_root)
            )
            paths.append(path)
            if progress is not None:
                progress(index, total, match_id, cached)
            continue

        cached = False
        if not refresh:
            try:
                data = load_australian_football_match(match_id, raw_root)
                if data.details.date.year != manifest.year:
                    raise ValueError(
                        f"Historical match {match_id} belongs to "
                        f"{data.details.date.year}, expected {manifest.year}"
                    )
                cached = True
            except FileNotFoundError:
                pass
        if cached:
            path = australian_football_match_cache_path(match_id, raw_root)
        else:
            if made_live_request and delay_ms:
                time_module.sleep(delay_ms / 1000)
            path = scrape_australian_football_match(
                browser, match_id, manifest.year, raw_root
            )
            made_live_request = True
        paths.append(path)
        if progress is not None:
            progress(index, total, match_id, cached)
    return paths
