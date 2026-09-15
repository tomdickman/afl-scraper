"""Tests for read-only AFL Official season cache preflight."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from afl_scraper.pipelines.official import (
    OfficialSeasonCacheReport,
    inspect_official_season_cache,
    preflight_official_season_cache,
)
from afl_scraper.scraper import save_raw_match_data, save_season_manifest
from afl_scraper.scraper.models import (
    DiscoveredRound,
    RawMatchData,
    RawMatchDetails,
    RawPlayerStat,
    SeasonManifest,
)


def _stat(official_id: str, name: str) -> RawPlayerStat:
    return RawPlayerStat(
        afl_official_id=official_id,
        player_name=name,
        jumper_number=1,
        kicks=1,
        handballs=1,
        disposals=2,
        marks=1,
        goals=0,
        behinds=0,
        hitouts=0,
        tackles=1,
        clearances=0,
        goal_assists=0,
        time_on_ground_percent=Decimal("80"),
        fantasy_points=10,
    )


def _match(
    *,
    year: int = 2012,
    home_name: str = "Alex Smith",
    home_id: str = "101",
) -> RawMatchData:
    return RawMatchData(
        details=RawMatchDetails(
            home_team="Carlton",
            away_team="Collingwood",
            round="Round 1",
            date=f"Saturday 24 March {year}",
            time="7:30 PM (GMT+10)",
            venue="MCG",
            status="FULL TIME",
            home_team_goals=1,
            home_team_behinds=1,
            home_team_total=7,
            away_team_goals=1,
            away_team_behinds=2,
            away_team_total=8,
        ),
        home_team_stats=[_stat(home_id, home_name)],
        away_team_stats=[_stat("202", "Bob Jones")],
    )


def _manifest(match_ids=(100, 101)) -> SeasonManifest:
    return SeasonManifest(
        year=2012,
        season_id=2,
        fixture_url="https://www.afl.com.au/fixture?Competition=1&Season=2",
        discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=list(match_ids))],
    )


def _roots(tmp_path):
    return tmp_path / "season", tmp_path / "match"


def test_complete_cache_preflight_returns_typed_report_without_writes(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest(), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)
    save_raw_match_data(_match(home_name="Chris Green", home_id="303"), 101, raw_root)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    report = preflight_official_season_cache(
        2012, manifest_root=manifest_root, raw_root=raw_root
    )

    assert report == OfficialSeasonCacheReport(
        year=2012,
        expected_matches=2,
        cached_matches=2,
        player_stats=4,
        participants=3,
    )
    assert report.ok
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_inspection_reports_missing_cache_and_strict_preflight_rejects_it(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest(), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)

    report = inspect_official_season_cache(
        2012, manifest_root=manifest_root, raw_root=raw_root
    )

    assert report.cached_matches == 1
    assert report.player_stats == 2
    assert report.missing_match_ids == (101,)
    assert not report.ok
    with pytest.raises(ValueError, match="missing 1 match caches: 101"):
        preflight_official_season_cache(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )


def test_invalid_manifest_member_fails_closed(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest((100,)), manifest_root)
    path = save_raw_match_data(_match(), 100, raw_root)
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid AFL Official cache for match 100"):
        preflight_official_season_cache(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    assert path.read_text(encoding="utf-8") == "not json"


def test_wrong_year_cache_is_rejected(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest((100,)), manifest_root)
    save_raw_match_data(_match(year=2013), 100, raw_root)

    with pytest.raises(ValueError, match="belongs to 2013, expected 2012"):
        preflight_official_season_cache(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )


def test_player_identity_drift_is_rejected(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest(), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)
    save_raw_match_data(_match(home_name="Another Person"), 101, raw_root)

    with pytest.raises(ValueError, match="Conflicting AFL official identity 101"):
        preflight_official_season_cache(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )


def test_valid_same_year_cache_outside_manifest_is_unexpected(tmp_path):
    manifest_root, raw_root = _roots(tmp_path)
    save_season_manifest(_manifest((100,)), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)
    save_raw_match_data(_match(home_name="Chris Green", home_id="303"), 999, raw_root)
    save_raw_match_data(_match(year=2013), 1000, raw_root)

    report = inspect_official_season_cache(
        2012, manifest_root=manifest_root, raw_root=raw_root
    )

    assert report.unexpected_match_ids == (999,)
    with pytest.raises(ValueError, match="unexpected 1 match caches: 999"):
        preflight_official_season_cache(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )
