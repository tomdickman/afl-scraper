from datetime import datetime, timezone
from pathlib import Path

import pytest

import afl_scraper.scraper.metadata_fallback as metadata_fallback
from afl_scraper.scraper.match_metadata import parse_afl_tables_match_catalog
from afl_scraper.scraper.metadata_fallback import (
    cross_check_official_match_details,
    resolve_fallback_match_details,
)
from afl_scraper.scraper.metadata_audit import audit_match_metadata
from afl_scraper.scraper.models import (
    DiscoveredRound,
    MatchMetadataCatalog,
    OfficialFixtureMetadata,
    SeasonManifest,
)
from afl_scraper.transform.match import parse_match_datetime


FIXTURE = Path(__file__).parent / "fixtures/afl_tables_2013_match_292_season.html"


def test_jsonc_config_is_cached_per_path(tmp_path):
    path = tmp_path / "config.jsonc"
    path.write_text('{"venue": "first"}', encoding="utf-8")
    metadata_fallback._load_jsonc.cache_clear()
    try:
        assert metadata_fallback._load_jsonc(path) == {"venue": "first"}
        path.write_text('{"venue": "second"}', encoding="utf-8")
        assert metadata_fallback._load_jsonc(path) == {"venue": "first"}
    finally:
        metadata_fallback._load_jsonc.cache_clear()


def _catalog():
    return parse_afl_tables_match_catalog(
        FIXTURE.read_text(encoding="utf-8"),
        2013,
        source_url="https://afltables.com/afl/seas/2013.html",
        fetched_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )


def _official_fixture(**changes):
    values = {
        "match_id": 292,
        "provider_id": "CD_M20130140502",
        "round": "5",
        "home_team": "St Kilda",
        "away_team": "Sydney Swans",
        "scheduled_at": datetime.fromisoformat("2013-04-25T17:50:00+10:00"),
        "venue": "Westpac Stadium, Wellington",
        "home_total": 63,
        "away_total": 79,
        "status": "COMPLETED",
        "source_url": "https://www.afl.com.au/afl/matches/292",
    }
    values.update(changes)
    return OfficialFixtureMetadata(**values)


def test_parses_match_292_from_afl_tables_season_html():
    catalog = _catalog()

    assert len(catalog.matches) == 1
    match = catalog.matches[0]
    assert match.source_match_id == "151620130425"
    assert match.round == "Round 5"
    assert match.home_team == "St Kilda"
    assert match.away_team == "Sydney"
    assert match.venue == "Wellington"
    assert match.local_time.isoformat() == "19:50:00"
    assert (match.home_goals, match.home_behinds, match.home_total) == (9, 9, 63)
    assert (match.away_goals, match.away_behinds, match.away_total) == (11, 13, 79)


def test_match_292_fallback_cross_checks_instant_and_preserves_local_time():
    details, provenance = resolve_fallback_match_details(
        _official_fixture(), _catalog()
    )

    assert details.home_team == "St Kilda"
    assert details.away_team == "Sydney Swans"
    assert details.round == "5"
    assert details.date == "Thursday 25 April 2013"
    assert details.time == "7:50 PM (GMT+12:00)"
    assert details.venue == "Westpac Stadium, Wellington"
    assert parse_match_datetime(details.date, details.time).isoformat() == (
        "2013-04-25T19:50:00+12:00"
    )
    assert provenance.match_details_source == "afl_tables"
    assert provenance.match_details_url.endswith("151620130425.html")
    assert "scheduled_at" in provenance.cross_checked_fields


def test_conflicting_fixture_score_fails_without_selecting_fallback():
    with pytest.raises(ValueError, match="resolved to 0"):
        resolve_fallback_match_details(_official_fixture(home_total=64), _catalog())


def test_ambiguous_external_candidates_fail_closed():
    catalog = _catalog()
    duplicate = catalog.matches[0].model_copy(
        update={
            "source_match_id": "another-id",
            "source_url": "https://afltables.com/another-id.html",
        }
    )
    ambiguous = MatchMetadataCatalog(
        year=2013,
        source_url=catalog.source_url,
        fetched_at=catalog.fetched_at,
        matches=[catalog.matches[0], duplicate],
    )

    with pytest.raises(ValueError, match="resolved to 2"):
        resolve_fallback_match_details(_official_fixture(), ambiguous)


def test_fallback_requires_enriched_official_fixture():
    with pytest.raises(ValueError, match="schema-version-2"):
        resolve_fallback_match_details(None, _catalog())


def test_official_finals_week_matches_specific_external_final():
    catalog = _catalog()
    finals_catalog = catalog.model_copy(
        update={
            "matches": [
                catalog.matches[0].model_copy(update={"round": "Qualifying Final"})
            ]
        }
    )

    details, _provenance = resolve_fallback_match_details(
        _official_fixture(round="FW1"), finals_catalog
    )

    assert details.round == "FW1"


def test_complete_official_details_are_cross_checked_field_by_field():
    external, _provenance = resolve_fallback_match_details(
        _official_fixture(), _catalog()
    )

    cross_check_official_match_details(external, external)

    conflicting = external.model_copy(update={"away_team_total": 80})
    with pytest.raises(ValueError, match="away_total=80 vs 79"):
        cross_check_official_match_details(conflicting, external)


@pytest.mark.parametrize(
    ("official_round", "external_round"),
    [
        ("Finals Week 1", "FW1"),
        ("Qualifying Finals", "QF"),
        ("Elimination Finals", "EF"),
        ("Semi Finals", "SF"),
        ("Preliminary Finals", "PF"),
        ("Grand Final", "GF"),
    ],
)
def test_cross_check_accepts_equivalent_finals_round_names(
    official_round, external_round
):
    external, _provenance = resolve_fallback_match_details(
        _official_fixture(), _catalog()
    )

    cross_check_official_match_details(
        external.model_copy(update={"round": official_round}),
        external.model_copy(update={"round": external_round}),
    )


def test_cache_only_audit_reports_every_manifest_member():
    fixture = _official_fixture()
    manifest = SeasonManifest(
        schema_version=2,
        year=2013,
        season_id=4,
        fixture_url="https://www.afl.com.au/fixture?Season=11",
        discovered_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="5", match_ids=[292])],
        fixtures=[fixture],
    )

    report = audit_match_metadata(manifest, _catalog())

    assert report["match_count"] == 1
    assert report["resolved_count"] == 1
    assert report["unresolved_count"] == 0
    assert report["matches"][0]["external_url"].endswith("151620130425.html")
