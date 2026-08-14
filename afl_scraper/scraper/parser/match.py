import re
from decimal import Decimal, InvalidOperation

from playwright.sync_api import Locator, Page, expect

from ..constants import FIXTURE_CLASSNAMES
from ..models import RawMatchData, RawMatchDetails, RawPlayerStat


_PLAYER_ID_PATTERN = re.compile(r"/players/(?P<player_id>\d+)(?:/|$)")
_COMPLETED_STATUS = "FULL TIME"
_EXPECTED_PLAYERS_PER_TEAM = 23

_HEADER_ALIASES = {
    "#": "jumper_number",
    "PLAYER": "player_name",
    "AF": "fantasy_points",
    "G": "goals",
    "B": "behinds",
    "D": "disposals",
    "K": "kicks",
    "H": "handballs",
    "HB": "handballs",
    "M": "marks",
    "T": "tackles",
    "HO": "hitouts",
    "CLR": "clearances",
    "CL": "clearances",
    "MG": "metres_gained",
    "GA": "goal_assists",
    "TOG%": "time_on_ground_percent",
    "R50": "rebound_50s",
    "I50": "inside_50s",
    "CG": "clangers",
    "FF": "free_kicks_for",
    "FA": "free_kicks_against",
    "CP": "contested_possessions",
    "UP": "uncontested_possessions",
    "CM": "contested_marks",
    "MI5": "marks_inside_50",
    "1%": "one_percenters",
    "BO": "bounces",
}

_REQUIRED_FIELDS = {
    "jumper_number",
    "player_name",
    "fantasy_points",
    "goals",
    "behinds",
    "kicks",
    "handballs",
    "marks",
    "tackles",
    "hitouts",
    "clearances",
    "goal_assists",
    "time_on_ground_percent",
}

_DECIMAL_FIELDS = {"time_on_ground_percent"}
_TEXT_FIELDS = {"player_name"}


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _extract_match_details(page: Page) -> RawMatchDetails:
    teams_text = _normalize_text(
        page.locator(FIXTURE_CLASSNAMES["MATCH_TEAMS"]).inner_text()
    )
    teams = re.split(r"\s+v\s+", teams_text)
    if len(teams) != 2 or not all(teams):
        raise ValueError(f"Could not parse two team names from {teams_text!r}")

    date_time_text = page.locator(FIXTURE_CLASSNAMES["MATCH_DATE_TIME"]).inner_text()
    date_time_parts = [_normalize_text(part) for part in date_time_text.split("•")]
    if len(date_time_parts) != 3 or not all(date_time_parts):
        raise ValueError(f"Could not parse round/date/time from {date_time_text!r}")
    round_name, date_info, time_info = date_time_parts

    venue_text = page.locator(FIXTURE_CLASSNAMES["MATCH_VENUE"]).inner_text()
    venue = _normalize_text(venue_text.partition("•")[0]).rstrip(",")
    if not venue:
        raise ValueError(f"Could not parse venue from {venue_text!r}")

    status = _normalize_text(
        page.locator(".mc-header__status-label").inner_text()
    ).upper()
    if status != _COMPLETED_STATUS:
        raise ValueError(
            f"Player statistics are only accepted for completed matches; got {status!r}"
        )

    totals = page.locator(FIXTURE_CLASSNAMES["MATCH_SCORE_TOTALS"]).all_inner_texts()
    score_splits = page.locator(
        FIXTURE_CLASSNAMES["MATCH_SCORE_SPLITS"]
    ).all_inner_texts()
    if len(totals) != 2 or len(score_splits) != 2:
        raise ValueError(
            "Expected exactly two score totals and two goal/behind score splits"
        )

    home_total, away_total = (_parse_integer(value, "score total") for value in totals)
    home_goals, home_behinds = _parse_score_split(score_splits[0])
    away_goals, away_behinds = _parse_score_split(score_splits[1])
    if home_goals * 6 + home_behinds != home_total:
        raise ValueError("Home score total does not equal goals * 6 + behinds")
    if away_goals * 6 + away_behinds != away_total:
        raise ValueError("Away score total does not equal goals * 6 + behinds")

    return RawMatchDetails(
        home_team=teams[0],
        away_team=teams[1],
        round=round_name,
        date=date_info,
        time=time_info,
        venue=venue,
        status=status,
        home_team_goals=home_goals,
        home_team_behinds=home_behinds,
        home_team_total=home_total,
        away_team_goals=away_goals,
        away_team_behinds=away_behinds,
        away_team_total=away_total,
    )


def _parse_score_split(value: str) -> tuple[int, int]:
    parts = _normalize_text(value).split(".")
    if len(parts) != 2:
        raise ValueError(f"Invalid goal/behind score split: {value!r}")
    return (
        _parse_integer(parts[0], "goals"),
        _parse_integer(parts[1], "behinds"),
    )


def display_player_stats(page: Page) -> Page:
    player_stats_btn = page.get_by_role("tab", name="Player Stats")
    player_stats_btn.click()
    page.locator(".stats-table__table").wait_for(state="visible")
    return page


def _extract_header_columns(table: Locator) -> list[str]:
    return [
        _normalize_text(value) for value in table.locator("thead th").all_inner_texts()
    ]


def _canonical_fields(columns: list[str]) -> list[str | None]:
    fields = [_HEADER_ALIASES.get(_normalize_header(column)) for column in columns]
    present = {field for field in fields if field is not None}
    missing = sorted(_REQUIRED_FIELDS - present)
    if missing:
        raise ValueError(f"Player stats table is missing required fields: {missing}")

    duplicates = sorted(field for field in present if fields.count(field) > 1)
    if duplicates:
        raise ValueError(f"Player stats table has duplicate fields: {duplicates}")
    return fields


def _parse_integer(value: str, field: str) -> int:
    normalized = _normalize_text(value)
    if normalized == "-":
        return 0
    if not normalized:
        raise ValueError(f"Missing integer value for {field}")
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {field}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"Negative integer value for {field}: {parsed}")
    return parsed


def _parse_decimal(value: str, field: str) -> Decimal:
    normalized = _normalize_text(value).rstrip("%")
    if normalized == "-":
        return Decimal("0")
    if not normalized:
        raise ValueError(f"Missing decimal value for {field}")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value for {field}: {value!r}") from exc


def _player_id_from_href(href: str | None) -> str:
    match = _PLAYER_ID_PATTERN.search(href or "")
    if match is None:
        raise ValueError(f"Could not parse AFL official player ID from {href!r}")
    return match.group("player_id")


def _parse_player_stat(
    columns: list[str], values: list[str], player_href: str | None
) -> RawPlayerStat:
    if len(columns) != len(values):
        raise ValueError(
            f"Player row has {len(values)} cells for {len(columns)} headers"
        )

    fields = _canonical_fields(columns)
    parsed: dict[str, object] = {}
    extra_stats: dict[str, str] = {}
    for column, field, value in zip(columns, fields, values, strict=True):
        if field is None:
            extra_stats[column] = _normalize_text(value)
        elif field in _TEXT_FIELDS:
            parsed[field] = _normalize_text(value)
        elif field in _DECIMAL_FIELDS:
            parsed[field] = _parse_decimal(value, field)
        else:
            parsed[field] = _parse_integer(value, field)

    parsed["afl_official_id"] = _player_id_from_href(player_href)
    parsed["extra_stats"] = extra_stats
    return RawPlayerStat.model_validate(parsed)


def _extract_team_stats(table: Locator) -> list[RawPlayerStat]:
    columns = _extract_header_columns(table)
    if not columns:
        raise ValueError("No column headers found in player stats table")
    _canonical_fields(columns)

    rows = table.locator("tbody tr").all()
    stats: list[RawPlayerStat] = []
    for row in rows:
        values = [
            _normalize_text(value) for value in row.locator("th, td").all_inner_texts()
        ]
        player_link = row.locator('a[href*="/players/"]').first
        href = player_link.get_attribute("href") if player_link.count() else None
        stats.append(_parse_player_stat(columns, values, href))
    return stats


def _first_player_href(table: Locator) -> str | None:
    first_link = table.locator('tbody tr a[href*="/players/"]').first
    return first_link.get_attribute("href") if first_link.count() else None


def _select_team(
    page: Page, table: Locator, option_index: int, previous_first_href: str | None
) -> str:
    selector = page.locator("button#teams-dropdown-button")
    selector.click()
    options = page.locator('.select__options-wrapper [role="option"]')
    options.first.wait_for(state="visible")
    if options.count() != 3 or _normalize_text(options.first.inner_text()) != "Both":
        raise ValueError("Expected AFL team selector options: Both, home, away")

    option = options.nth(option_index)
    label = _normalize_text(option.inner_text())
    option.click()
    expect(selector).to_contain_text(label)
    page.wait_for_function(
        """
        ({ previousHref }) => {
          const link = document.querySelector(
            '.stats-table__table tbody tr a[href*="/players/"]'
          );
          const href = link?.getAttribute('href');
          return Boolean(href) && (!previousHref || href !== previousHref);
        }
        """,
        arg={"previousHref": previous_first_href},
    )
    current_href = _first_player_href(table)
    if current_href is None:
        raise ValueError(f"No player link appeared after selecting {label!r}")
    return current_href


def _validate_team_stats(
    home_stats: list[RawPlayerStat], away_stats: list[RawPlayerStat]
) -> None:
    if len(home_stats) != _EXPECTED_PLAYERS_PER_TEAM:
        raise ValueError(
            f"Expected {_EXPECTED_PLAYERS_PER_TEAM} home players, got {len(home_stats)}"
        )
    if len(away_stats) != _EXPECTED_PLAYERS_PER_TEAM:
        raise ValueError(
            f"Expected {_EXPECTED_PLAYERS_PER_TEAM} away players, got {len(away_stats)}"
        )

    home_ids = [stat.afl_official_id for stat in home_stats]
    away_ids = [stat.afl_official_id for stat in away_stats]
    if len(home_ids) != len(set(home_ids)):
        raise ValueError("Home player statistics contain duplicate official IDs")
    if len(away_ids) != len(set(away_ids)):
        raise ValueError("Away player statistics contain duplicate official IDs")
    overlap = sorted(set(home_ids) & set(away_ids))
    if overlap:
        raise ValueError(f"Players appeared for both teams: {overlap}")


def extract_table_data(page: Page) -> RawMatchData:
    """Extract and validate a completed match from the AFL match centre."""
    table = page.locator(".stats-table__table")
    if table.count() != 1:
        raise ValueError(f"Expected one player stats table, found {table.count()}")

    details = _extract_match_details(page)
    home_first_href = _select_team(page, table, 1, None)
    home_stats = _extract_team_stats(table)
    _select_team(page, table, 2, home_first_href)
    away_stats = _extract_team_stats(table)
    _validate_team_stats(home_stats, away_stats)

    return RawMatchData(
        details=details,
        home_team_stats=home_stats,
        away_team_stats=away_stats,
    )
