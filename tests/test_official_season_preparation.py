"""Tests for read-only AFL Official season preparation."""

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from afl_scraper.pipelines import official_season
from afl_scraper.scraper import save_raw_match_data, save_season_manifest
from afl_scraper.scraper.constants import official_season_id
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
    home_id: str = "101",
    home_name: str = "Alex Smith",
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


def _manifest(match_ids=(100, 101), *, year: int = 2012) -> SeasonManifest:
    return SeasonManifest(
        year=year,
        season_id=official_season_id(year),
        fixture_url=f"https://www.afl.com.au/fixture?year={year}",
        discovered_at=datetime(2026, 8, 15, tzinfo=UTC),
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
    monkeypatch.setattr(official_season, "connection_pool", _pool(connection))

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


def test_preflight_excludes_cancelled_fixture_from_loading(monkeypatch, tmp_path):
    manifest_root = tmp_path / "season"
    raw_root = tmp_path / "match"
    save_season_manifest(_manifest((847, 848), year=2015), manifest_root)
    save_raw_match_data(_match(year=2015), 848, raw_root)
    connection, _ = _connection(
        [
            [("101", "Alex_Smith"), ("202", "Bob_Jones")],
            [("Alex_Smith",), ("Bob_Jones",)],
            [("Carlton",), ("Collingwood",)],
            [("M.C.G.",)],
        ]
    )
    load_match = MagicMock(wraps=official_season.load_raw_match_data)
    monkeypatch.setattr(official_season, "load_raw_match_data", load_match)

    prepared = official_season.preflight_official_season(
        connection, 2015, manifest_root=manifest_root, raw_root=raw_root
    )

    assert [match.source_match_id for match in prepared] == ["848"]
    assert [call.args[0] for call in load_match.call_args_list] == [848, 848]


def test_incomplete_cache_fails_before_database_is_opened(monkeypatch, tmp_path):
    manifest_root = tmp_path / "season"
    raw_root = tmp_path / "match"
    save_season_manifest(_manifest(), manifest_root)
    save_raw_match_data(_match(), 100, raw_root)
    pool = MagicMock()
    monkeypatch.setattr(official_season, "connection_pool", pool)

    with pytest.raises(ValueError, match="missing 1 match caches: 101"):
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    pool.assert_not_called()


def test_missing_player_mapping_fails_before_transform(monkeypatch, tmp_path):
    manifest_root, raw_root = _complete_cache(tmp_path, (100,))
    connection, cursor = _connection([[("101", "Alex_Smith")]])
    monkeypatch.setattr(official_season, "connection_pool", _pool(connection))
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
    monkeypatch.setattr(official_season, "connection_pool", _pool(connection))

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
    monkeypatch.setattr(official_season, "connection_pool", _pool(connection))

    with pytest.raises(ValueError, match="aliases two participants.*100"):
        official_season.prepare_official_season(
            2012, manifest_root=manifest_root, raw_root=raw_root
        )

    cursor.execute.assert_called_once()
    connection.transaction.assert_not_called()


def test_grouped_first_final_is_resolved_before_transform(monkeypatch, tmp_path):
    manifest_root, raw_root = _complete_cache(tmp_path, (100,))
    cached = _match()
    cached = cached.model_copy(
        update={"details": cached.details.model_copy(update={"round": "Finals Week 1"})}
    )
    save_raw_match_data(cached, 100, raw_root)
    connection, _ = _connection(
        [
            [("101", "Alex_Smith"), ("202", "Bob_Jones")],
            [("Alex_Smith",), ("Bob_Jones",)],
            [("Carlton",), ("Collingwood",)],
            [("M.C.G.",)],
        ]
    )
    monkeypatch.setattr(official_season, "connection_pool", _pool(connection))
    load_catalog = MagicMock(return_value=object())
    load_finals = MagicMock(return_value=[])
    resolve = MagicMock(return_value="EF")
    monkeypatch.setattr(official_season, "load_match_metadata_catalog", load_catalog)
    monkeypatch.setattr(
        official_season, "_australian_football_first_finals", load_finals
    )
    monkeypatch.setattr(official_season, "_resolve_grouped_first_final", resolve)

    prepared = official_season.prepare_official_season(
        2012, manifest_root=manifest_root, raw_root=raw_root
    )

    assert prepared[0].game.round == "EF"
    load_catalog.assert_called_once()
    load_finals.assert_called_once()
    resolve.assert_called_once()


def test_grouped_first_final_requires_external_sources_to_agree(monkeypatch):
    raw_match = _match()
    raw_match = raw_match.model_copy(
        update={
            "details": raw_match.details.model_copy(update={"round": "Finals Week 1"})
        }
    )
    australian_football_match = MagicMock()
    australian_football_match.details.round = "1EF"
    afl_tables_record = MagicMock(source_match_id="tables-1", round="QF")
    manifest = MagicMock()
    monkeypatch.setattr(
        official_season,
        "resolve_fallback_match_record",
        MagicMock(return_value=afl_tables_record),
    )
    monkeypatch.setattr(
        official_season,
        "_australian_football_candidate_matches",
        MagicMock(return_value=True),
    )

    with pytest.raises(ValueError, match="Conflicting first-finals classification"):
        official_season._resolve_grouped_first_final(
            100,
            raw_match,
            manifest,
            object(),
            [(200, australian_football_match)],
        )
