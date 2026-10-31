"""Source-neutral normalization shared by scraping and transformation layers."""

import re
from datetime import datetime, timedelta, timezone

from .config import load_config
from .team_mappings import TEAM_MAPPINGS


def canonical_team(value: str) -> str:
    """Resolve a provider team label to its canonical database identifier."""
    normalized = " ".join(value.casefold().split())
    try:
        return TEAM_MAPPINGS[normalized]
    except KeyError as error:
        raise ValueError(f"No team ID mapping found for {value}") from error


_TEAM_ALIASES = {
    alias: canonical.casefold() for alias, canonical in TEAM_MAPPINGS.items()
}
_TEAM_ALIASES.update(
    {
        "footscray": "western bulldogs",
        "greater western sydney": "gws",
        "gws giants": "gws",
        "gws": "gws",
    }
)


def normalize_team(value: str) -> str:
    """Normalize a team label for conservative cross-source comparison."""
    normalized = " ".join(value.casefold().strip().split())
    return _TEAM_ALIASES.get(normalized, normalized)


def _normalize_venue(value: str, *, collapse_spaces: bool = False) -> str:
    normalized = " ".join(value.replace("\xa0", " ").split()).casefold()
    return normalized.replace(" ", "") if collapse_spaces else normalized


def canonical_venue(venue_name: str, source: str = "afl_official") -> str:
    """Resolve a source venue label to its canonical database identifier."""
    mappings = load_config("venue_name_mappings.jsonc").get(source, {})
    cleaned = " ".join(venue_name.replace("\xa0", " ").split()).strip(" ,")
    candidates = [cleaned]
    if "," in cleaned:
        candidates.append(cleaned.rsplit(",", 1)[0].strip())

    for candidate in candidates:
        for key, value in mappings.items():
            if _normalize_venue(key) == _normalize_venue(candidate):
                return value
            if _normalize_venue(key, collapse_spaces=True) == _normalize_venue(
                candidate, collapse_spaces=True
            ):
                return value
    raise KeyError(f"No venue mapping found for {venue_name!r} (source: {source})")


_DATE_FORMATS = ("%A %d %B %Y", "%a %d %b %Y", "%d %b %Y")
_CLOCK_FORMATS = ("%I:%M %p", "%I:%M%p", "%H:%M")
_TIMEZONE_PATTERN = re.compile(
    r"^(?P<clock>.+?)\s*\(GMT(?P<sign>[+-])(?P<hours>\d{1,2})"
    r"(?::?(?P<minutes>\d{2}))?\)$",
    re.IGNORECASE,
)


def parse_aware_datetime(date_str: str, time_str: str) -> datetime:
    """Parse an AFL date and a clock containing an explicit numeric offset."""
    normalized_date = " ".join(date_str.split())
    normalized_time = " ".join(time_str.split())
    timezone_match = _TIMEZONE_PATTERN.fullmatch(normalized_time)
    if timezone_match is None:
        raise ValueError(f"Match time must include a numeric GMT offset: {time_str!r}")

    hours = int(timezone_match.group("hours"))
    minutes = int(timezone_match.group("minutes") or "0")
    if hours > 14 or minutes >= 60:
        raise ValueError(f"Invalid GMT offset in match time: {time_str!r}")
    direction = 1 if timezone_match.group("sign") == "+" else -1
    offset = timezone(direction * timedelta(hours=hours, minutes=minutes))
    clock = timezone_match.group("clock").strip()

    for date_format in _DATE_FORMATS:
        for clock_format in _CLOCK_FORMATS:
            try:
                parsed = datetime.strptime(
                    f"{normalized_date} {clock}", f"{date_format} {clock_format}"
                )
                return parsed.replace(tzinfo=offset)
            except ValueError:
                continue
    raise ValueError(
        f"Could not parse match datetime: date={date_str!r} time={time_str!r}"
    )


__all__ = [
    "canonical_team",
    "canonical_venue",
    "normalize_team",
    "parse_aware_datetime",
]
