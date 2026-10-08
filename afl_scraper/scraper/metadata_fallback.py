"""Deterministic reconciliation of official fixtures with external metadata."""

import json
import re
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..transform.match import parse_match_datetime, resolve_venue
from ..transformer.teams import transform_team_name
from .models import (
    MatchDataProvenance,
    MatchMetadataCatalog,
    MatchMetadataRecord,
    OfficialFixtureMetadata,
    RawMatchDetails,
)


_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
_FINAL_ROUNDS = {
    "qf": "qf",
    "qualifying final": "qf",
    "qualifying finals": "qf",
    "ef": "ef",
    "elimination final": "ef",
    "elimination finals": "ef",
    "sf": "sf",
    "semi final": "sf",
    "semi finals": "sf",
    "pf": "pf",
    "preliminary final": "pf",
    "preliminary finals": "pf",
    "gf": "gf",
    "grand final": "gf",
    "grand finals": "gf",
}
_OFFICIAL_FINALS_WEEKS = {
    "fw1": {"qf", "ef"},
    "finals week 1": {"qf", "ef"},
    "fw2": {"sf"},
    "finals week 2": {"sf"},
    "fw3": {"pf"},
    "finals week 3": {"pf"},
    "fw4": {"gf"},
    "finals week 4": {"gf"},
}


@cache
def _load_jsonc(path: Path) -> dict:
    return json.loads(re.sub(r"//.*", "", path.read_text(encoding="utf-8")))


def _round_key(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    if normalized.startswith("round "):
        normalized = normalized.removeprefix("round ")
    return _FINAL_ROUNDS.get(normalized, normalized)


def _rounds_match(official: str, external: str) -> bool:
    official_key = _round_key(official)
    external_key = _round_key(external)
    if official_key == external_key:
        return True
    allowed = _OFFICIAL_FINALS_WEEKS.get(official_key)
    external_group = _OFFICIAL_FINALS_WEEKS.get(external_key)
    if allowed is not None and external_group is not None:
        return allowed == external_group
    return (
        external_key in allowed if allowed is not None else official_key == external_key
    )


def _external_datetime(record: MatchMetadataRecord) -> datetime:
    venue_id = resolve_venue(record.venue, "afl_tables")
    timezone_name = _load_jsonc(_CONFIG_ROOT / "venue_timezones.jsonc").get(venue_id)
    if timezone_name is None:
        raise KeyError(f"No timezone mapping found for canonical venue {venue_id!r}")
    try:
        venue_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"Invalid IANA timezone {timezone_name!r} for venue {venue_id!r}"
        ) from error
    value = datetime.combine(record.local_date, record.local_time).replace(
        tzinfo=venue_timezone
    )
    round_trip = value.astimezone(timezone.utc).astimezone(venue_timezone)
    if round_trip.replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError(
            f"Nonexistent local match time {value.replace(tzinfo=None).isoformat()} "
            f"at {venue_id}"
        )
    return value


def _candidate_matches(
    fixture: OfficialFixtureMetadata, record: MatchMetadataRecord
) -> bool:
    if transform_team_name(fixture.home_team) != transform_team_name(record.home_team):
        return False
    if transform_team_name(fixture.away_team) != transform_team_name(record.away_team):
        return False
    if not _rounds_match(fixture.round, record.round):
        return False
    if fixture.venue is None or fixture.scheduled_at is None:
        return False
    if resolve_venue(fixture.venue, "afl_official") != resolve_venue(
        record.venue, "afl_tables"
    ):
        return False
    if fixture.scheduled_at.astimezone(timezone.utc) != _external_datetime(
        record
    ).astimezone(timezone.utc):
        return False
    if fixture.home_total is not None and fixture.home_total != record.home_total:
        return False
    if fixture.away_total is not None and fixture.away_total != record.away_total:
        return False
    return True


def resolve_fallback_match_record(
    fixture: OfficialFixtureMetadata | None,
    catalog: MatchMetadataCatalog,
) -> MatchMetadataRecord:
    """Resolve one external record only after every fixture field agrees."""
    if fixture is None:
        raise ValueError(
            "Match metadata fallback requires a schema-version-2 official season "
            "manifest; refresh season discovery first"
        )
    if fixture.status != "COMPLETED":
        raise ValueError(
            f"Match {fixture.match_id} is not completed in the official fixture"
        )
    if fixture.venue is None or fixture.scheduled_at is None:
        raise ValueError(
            f"Official fixture {fixture.match_id} lacks venue or scheduled time"
        )

    candidates = [
        record
        for record in catalog.matches
        if record.year == catalog.year and _candidate_matches(fixture, record)
    ]
    if len(candidates) != 1:
        sample = ", ".join(record.source_url for record in candidates[:5]) or "none"
        raise ValueError(
            f"Official match {fixture.match_id} resolved to {len(candidates)} "
            f"AFL Tables metadata candidates; candidates={sample}"
        )
    return candidates[0]


def match_details_from_record(
    fixture: OfficialFixtureMetadata,
    record: MatchMetadataRecord,
) -> RawMatchDetails:
    """Synthesize the raw match-detail contract from a resolved record."""
    local_datetime = _external_datetime(record)
    offset = local_datetime.utcoffset()
    if offset is None:
        raise ValueError(f"External match {record.source_match_id} has no UTC offset")
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    clock = local_datetime.strftime("%I:%M %p").lstrip("0")
    time_text = f"{clock} (GMT{sign}{hours:02d}:{minutes:02d})"
    details = RawMatchDetails(
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        round=fixture.round,
        date=record.local_date.strftime("%A %d %B %Y"),
        time=time_text,
        venue=fixture.venue,
        status="FULL TIME",
        home_team_goals=record.home_goals,
        home_team_behinds=record.home_behinds,
        home_team_total=record.home_total,
        away_team_goals=record.away_goals,
        away_team_behinds=record.away_behinds,
        away_team_total=record.away_total,
    )
    return details


def resolve_fallback_match_details(
    fixture: OfficialFixtureMetadata | None,
    catalog: MatchMetadataCatalog,
) -> tuple[RawMatchDetails, MatchDataProvenance]:
    """Resolve one unique external record from complete official fixture evidence."""
    record = resolve_fallback_match_record(fixture, catalog)
    assert fixture is not None
    details = match_details_from_record(fixture, record)
    provenance = MatchDataProvenance(
        player_stats_url=fixture.source_url,
        match_details_source="afl_tables",
        match_details_url=record.source_url,
        official_fixture_url=fixture.source_url,
        cross_checked_fields=(
            "year",
            "round",
            "home_team",
            "away_team",
            "scheduled_at",
            "venue",
            "home_total",
            "away_total",
        ),
        fallback_reason="official match header unavailable",
    )
    return details, provenance


def cross_check_official_match_details(
    official: RawMatchDetails,
    external: RawMatchDetails,
) -> None:
    """Fail with a field-level diagnostic when complete sources disagree."""
    comparisons = {
        "home_team": (
            transform_team_name(official.home_team),
            transform_team_name(external.home_team),
        ),
        "away_team": (
            transform_team_name(official.away_team),
            transform_team_name(external.away_team),
        ),
        "scheduled_at": (
            parse_match_datetime(official.date, official.time).astimezone(timezone.utc),
            parse_match_datetime(external.date, external.time).astimezone(timezone.utc),
        ),
        "venue": (
            resolve_venue(official.venue, "afl_official"),
            resolve_venue(external.venue, "afl_official"),
        ),
        "home_goals": (official.home_team_goals, external.home_team_goals),
        "home_behinds": (official.home_team_behinds, external.home_team_behinds),
        "home_total": (official.home_team_total, external.home_team_total),
        "away_goals": (official.away_team_goals, external.away_team_goals),
        "away_behinds": (official.away_team_behinds, external.away_team_behinds),
        "away_total": (official.away_team_total, external.away_team_total),
    }
    conflicts = {
        field: {"afl_official": values[0], "afl_tables": values[1]}
        for field, values in comparisons.items()
        if values[0] != values[1]
    }
    if not _rounds_match(official.round, external.round):
        conflicts["round"] = {
            "afl_official": official.round,
            "afl_tables": external.round,
        }
    if conflicts:
        raise ValueError(
            "AFL Official and AFL Tables match metadata conflict: "
            + "; ".join(
                f"{field}={values['afl_official']!r} vs {values['afl_tables']!r}"
                for field, values in conflicts.items()
            )
        )
