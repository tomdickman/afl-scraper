"""AFL Tables match-metadata catalogue extraction and caching."""

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext

from .models import MatchMetadataCatalog, MatchMetadataRecord


BASE_URL = "https://afltables.com/afl/"
_MATCH_LINK_PATTERN = re.compile(r"stats/games/(?P<year>\d{4})/(?P<id>[^/]+)\.html$")
_DATE_TIME_PATTERN = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?P<date>\d{1,2}-[A-Za-z]{3}-\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}\s+[AP]M)",
    re.IGNORECASE,
)
_ROUND_PATTERN = re.compile(
    r"^(Round\s+\d+|Qualifying Final|Elimination Final|Semi Final|"
    r"Preliminary Final|Grand Final)(?:\s|$)",
    re.IGNORECASE,
)
_OUTAGE_SIGNATURES = ("site is down", "awaiting solutions")


def afl_tables_season_url(year: int) -> str:
    return f"{BASE_URL}seas/{year}.html"


def metadata_catalog_path(
    year: int, raw_root: Path = Path("data/raw/afl_tables")
) -> Path:
    return raw_root / "season" / str(year) / "matches.json"


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _score_split(row: Tag) -> tuple[int, int, int]:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 3:
        raise ValueError("AFL Tables match score row is incomplete")
    progression = _normalize(cells[1].get_text(" ", strip=True))
    final_split = progression.split()[-1]
    # Extra-time matches show the final score in parentheses after the
    # regulation-time score, for example ``10.12 (10.14)``.
    if final_split.startswith("(") and final_split.endswith(")"):
        final_split = final_split[1:-1]
    parts = final_split.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid AFL Tables final score split {final_split!r}")
    total_text = _normalize(cells[2].get_text(" ", strip=True))
    if not total_text.isdigit():
        raise ValueError(f"Invalid AFL Tables score total {total_text!r}")
    return int(parts[0]), int(parts[1]), int(total_text)


def _round_label(table: Tag) -> str:
    for previous in table.find_all_previous("table"):
        text = _normalize(previous.get_text(" ", strip=True))
        match = _ROUND_PATTERN.match(text)
        if match is not None:
            return " ".join(match.group(1).split()).title()
    raise ValueError("Could not associate AFL Tables match with a round")


def _parse_match_table(
    table: Tag, link: Tag, year: int, source_url: str
) -> MatchMetadataRecord:
    # Browser-normalized HTML inserts a <tbody>, while saved source HTML may
    # expose rows directly. Accept both without consuming rows from nested tables.
    rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
    if len(rows) != 2:
        raise ValueError(f"AFL Tables match table has {len(rows)} rows; expected 2")
    row_cells = [row.find_all("td", recursive=False) for row in rows]
    if any(len(cells) < 4 for cells in row_cells):
        raise ValueError("AFL Tables match table has incomplete rows")

    teams = [_normalize(cells[0].get_text(" ", strip=True)) for cells in row_cells]
    if not all(teams):
        raise ValueError("AFL Tables match table has a blank team")
    home_goals, home_behinds, home_total = _score_split(rows[0])
    away_goals, away_behinds, away_total = _score_split(rows[1])

    details_text = _normalize(row_cells[0][3].get_text(" ", strip=True))
    date_time = _DATE_TIME_PATTERN.search(details_text)
    if date_time is None:
        raise ValueError(f"Could not parse AFL Tables match date from {details_text!r}")
    local_date = datetime.strptime(date_time.group("date"), "%d-%b-%Y").date()
    local_time = datetime.strptime(date_time.group("time"), "%I:%M %p").time()
    venue_link = row_cells[0][3].find("a", href=re.compile(r"venues/"))
    if venue_link is None:
        raise ValueError("AFL Tables match has no venue link")
    venue = _normalize(venue_link.get_text(" ", strip=True))

    href = link.get("href", "")
    link_match = _MATCH_LINK_PATTERN.search(urlparse(urljoin(source_url, href)).path)
    if link_match is None or int(link_match.group("year")) != year:
        raise ValueError(f"Invalid AFL Tables match link {href!r} for {year}")
    return MatchMetadataRecord(
        source_match_id=link_match.group("id"),
        source_url=urljoin(source_url, href),
        year=year,
        round=_round_label(table),
        home_team=teams[0],
        away_team=teams[1],
        local_date=local_date,
        local_time=local_time,
        venue=venue,
        home_goals=home_goals,
        home_behinds=home_behinds,
        home_total=home_total,
        away_goals=away_goals,
        away_behinds=away_behinds,
        away_total=away_total,
    )


def parse_afl_tables_match_catalog(
    html: str,
    year: int,
    *,
    source_url: str | None = None,
    fetched_at: datetime | None = None,
) -> MatchMetadataCatalog:
    """Parse every match from an AFL Tables season page."""
    if not html.strip():
        raise ValueError("AFL Tables season metadata page is empty")
    lowered = html.casefold()
    signature = next((value for value in _OUTAGE_SIGNATURES if value in lowered), None)
    if signature:
        raise RuntimeError(
            f"AFL Tables season metadata contains outage signature {signature!r}"
        )
    source_url = source_url or afl_tables_season_url(year)
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_tables: set[int] = set()
    for link in soup.find_all("a", href=_MATCH_LINK_PATTERN):
        table = link.find_parent("table")
        if table is None or id(table) in seen_tables:
            continue
        seen_tables.add(id(table))
        records.append(_parse_match_table(table, link, year, source_url))
    if not records:
        raise ValueError(f"AFL Tables season {year} contains no match metadata")
    return MatchMetadataCatalog(
        year=year,
        source_url=source_url,
        fetched_at=fetched_at or datetime.now(timezone.utc),
        matches=records,
    )


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_match_metadata_catalog(
    year: int, raw_root: Path = Path("data/raw/afl_tables")
) -> MatchMetadataCatalog:
    path = metadata_catalog_path(year, raw_root)
    if not path.exists():
        raise FileNotFoundError(
            f"AFL Tables match metadata catalogue not found: {path}"
        )
    catalog = MatchMetadataCatalog.model_validate_json(path.read_text(encoding="utf-8"))
    if catalog.year != year:
        raise ValueError(
            f"Metadata catalogue at {path} contains {catalog.year}, expected {year}"
        )
    return catalog


def get_match_metadata_catalog(
    browser: BrowserContext,
    year: int,
    *,
    refresh: bool = False,
    raw_root: Path = Path("data/raw/afl_tables"),
) -> MatchMetadataCatalog:
    """Load a valid catalogue or fetch and atomically cache the complete season."""
    if not refresh:
        try:
            return load_match_metadata_catalog(year, raw_root)
        except FileNotFoundError:
            pass

    url = afl_tables_season_url(year)
    page = browser.new_page()
    try:
        response = page.goto(url)
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"AFL Tables season metadata returned HTTP {status}")
        if page.url.rstrip("/") != url:
            raise RuntimeError(
                f"AFL Tables metadata navigated to unexpected URL {page.url!r}"
            )
        html = page.content()
        catalog = parse_afl_tables_match_catalog(html, year, source_url=url)
    finally:
        page.close()

    directory = metadata_catalog_path(year, raw_root).parent
    _atomic_text(directory / "season.html", html)
    _atomic_text(directory / "matches.json", catalog.model_dump_json(indent=2) + "\n")
    return catalog
