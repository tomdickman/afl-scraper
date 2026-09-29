"""Tests for read-only AFL Official season preparation."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from afl_scraper.pipelines import official_season
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
    home_id: str = "101",
    home_name: str = "Alex Smith",
) -> RawMatchData:
    return RawMatchData(
        details=RawMatchDetails(
            home_team="Carlton",
            away_team="Collingwood",
            round="Round 1",
            date="Saturday 24 March 2012",
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


def _complete_cache(tmp_path, match_ids=(100, 101)):
    manifest_root = tmp_path / "season"
    raw_root = tmp_path / "match"
    save_season_manifest(_manifest(match_ids), manifest_root)
    save_raw_match_data(_match(), match_ids[0], raw_root)
    if len(match_ids) > 1:
        save_raw_match_data(
            _match(home_id="303", home_name="Chris Green"),
            match_ids[1],
            raw_root,
        )
    return manifest_root, raw_root


def _pool(connection):
    @contextmanager
    def pool():
        yield connection

    return pool


def _connection(rows):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = rows
    return connection, cursor


def test_prepares_complete_season_with_canonical_players_and_no_writes(
    monkeypatch, tmp_path
):
    manifest_root, raw_root = _complete_cache(tmp_path)
    connection, cursor = _connection(
        [
            [("101", "Alex_Smith"), ("202", "Bob_Jones"), ("303", "Chris_Green")],
            [("Alex_Smith",), ("Bob_Jones",), ("Chris_Green",)],
            [("Carlton",), ("Collingwood",)],
            [("M.C.G.",)],
        ]
    )
    monkeypatch.setattr(official_season, "admin_connection_pool", _pool(connection))

    prepared = official_season.prepare_official_season(
        2012, manifest_root=manifest_root, raw_root=raw_root
    )

    assert [match.source_match_id for match in prepared] == ["100", "101"]
    assert [match.game.id for match in prepared] == [1, 2]
    assert [stat.player_id for stat in prepared[0].player_stats] == [
        "Alex_Smith",
        "Bob_Jones",
    ]
    assert [stat.player_id for stat in prepared[1].player_stats] == [
        "Chris_Green",
        "Bob_Jones",
    ]
    assert all(match.game.venue == "M.C.G." for match in prepared)
    assert cursor.execute.call_count == 4
    connection.transaction.assert_not_called()
    connection.commit.assert_not_called()
    connection.execute.assert_not_called()


def test_incomplete_cache_fails_before_database_is_opened(monkeypatch, tmp_path):
    manifest_root = tmp_path / "season"
    raw_root = tmp_path / "match"
    save_season_manifest(_manifest(), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)
    pool = MagicMock()
    monkeypatch.setattr(official_season, "admin_connection_pool", pool)

    with pytest.raises(ValueError, match="missing 1 match caches: 101"):
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    pool.assert_not_called()


def test_missing_player_mapping_fails_before_transform(monkeypatch, tmp_path):
    manifest_root, raw_root = _complete_cache(tmp_path, (100,))
    connection, cursor = _connection([[("101", "Alex_Smith")]])
    monkeypatch.setattr(official_season, "admin_connection_pool", _pool(connection))
    transform = MagicMock()
    monkeypatch.setattr(official_season, "transform_match", transform)

    with pytest.raises(ValueError, match="Missing 1.*202"):
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    transform.assert_not_called()
    cursor.execute.assert_called_once()
    connection.transaction.assert_not_called()


def test_missing_database_references_are_reported_together(monkeypatch, tmp_path):
    manifest_root, raw_root = _complete_cache(tmp_path, (100,))
    connection, _ = _connection(
        [
            [("101", "Alex_Smith"), ("202", "Bob_Jones")],
            [("Alex_Smith",), ("Bob_Jones",)],
            [("Carlton",)],
            [],
        ]
    )
    monkeypatch.setattr(official_season, "admin_connection_pool", _pool(connection))

    with pytest.raises(ValueError) as error:
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    assert "missing team rows: Collingwood" in str(error.value)
    assert "missing venue rows: M.C.G." in str(error.value)
    connection.transaction.assert_not_called()


def test_canonical_mapping_cannot_alias_match_participants(monkeypatch, tmp_path):
    manifest_root, raw_root = _complete_cache(tmp_path, (100,))
    connection, cursor = _connection([[("101", "Same_Player"), ("202", "Same_Player")]])
    monkeypatch.setattr(official_season, "admin_connection_pool", _pool(connection))

    with pytest.raises(ValueError, match="aliases two participants.*100"):
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    cursor.execute.assert_called_once()
    connection.transaction.assert_not_called()
