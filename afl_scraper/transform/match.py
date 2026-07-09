import json
import re
from datetime import datetime
from pathlib import Path

from ..transformer.teams import transform_team_name


def _load_jsonc(path: Path) -> dict:
    text = path.read_text()
    text = re.sub(r"//.*", "", text)
    return json.loads(text)


def _load_venue_mappings(source: str) -> dict[str, str]:
    path = Path("config/venue_name_mappings.jsonc")
    data = _load_jsonc(path)
    return data.get(source, {})


def resolve_venue(venue_name: str, source: str = "afl_official") -> str:
    mappings = _load_venue_mappings(source)

    if venue_name in mappings:
        return mappings[venue_name]

    venue_lower = venue_name.lower().strip()
    for key, val in mappings.items():
        if key.lower().strip() == venue_lower:
            return val

    collapsed = re.sub(r"\s+", "", venue_name).lower()
    for key, val in mappings.items():
        if re.sub(r"\s+", "", key).lower() == collapsed:
            return val

    raise KeyError(f"No venue mapping found for '{venue_name}' (source: {source})")


def resolve_team(team_name: str) -> str:
    return transform_team_name(team_name)


_DATETIME_FORMATS = [
    "%a %d %b %Y %I:%M%p",
    "%a %d %b %Y %H:%M",
    "%d %b %Y %I:%M%p",
    "%d %b %Y %H:%M",
]


def parse_match_datetime(date_str: str, time_str: str) -> datetime:
    combined = f"{date_str} {time_str}".strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse match datetime: date='{date_str}' time='{time_str}'")
