import json
import importlib
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

import afl_scraper.cli as cli_module
from afl_scraper.cli import cli
from afl_scraper.models.player import PlayerInfo
from afl_scraper.scraper.scrape_player_ids import save_player_id_snapshots


snapshot_module = importlib.import_module("afl_scraper.scraper.scrape_player_ids")


def player(player_id, source_team="Carlton"):
    return PlayerInfo(
        id=player_id,
        first_name="Alex",
        last_name="Smith",
        team=source_team,
        year=2026,
    )


def test_all_sources_are_validated_before_any_snapshot_is_replaced(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    mapping_dir = tmp_path / "data/mapping"
    mapping_dir.mkdir(parents=True)
    official_path = mapping_dir / "2026_afl_official.json"
    tables_path = mapping_dir / "2026_afl_tables.json"
    official_path.write_text('[{"old": "official"}]')
    tables_path.write_text('[{"old": "tables"}]')

    with pytest.raises(ValueError, match="empty afl_tables"):
        save_player_id_snapshots(
            {"afl_official": [player("101")], "afl_tables": []}, 2026
        )

    assert json.loads(official_path.read_text()) == [{"old": "official"}]
    assert json.loads(tables_path.read_text()) == [{"old": "tables"}]


def test_valid_sources_are_promoted_as_one_validated_batch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    paths = save_player_id_snapshots(
        {
            "afl_official": [player("101")],
            "afl_tables": [player("Alex_Smith")],
        },
        2026,
    )

    assert set(paths) == {"afl_official", "afl_tables"}
    assert json.loads(paths["afl_official"].read_text())[0]["id"] == "101"
    assert json.loads(paths["afl_tables"].read_text())[0]["id"] == "Alex_Smith"
    assert not [
        path for path in paths["afl_official"].parent.iterdir() if path.suffix == ".tmp"
    ]


def test_backup_cleanup_failure_does_not_fail_or_block_future_promotions(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.chdir(tmp_path)
    mapping_dir = tmp_path / "data/mapping"
    mapping_dir.mkdir(parents=True)
    official_path = mapping_dir / "2026_afl_official.json"
    official_path.write_text("old official")
    real_unlink = type(official_path).unlink

    def fail_backup_cleanup(path, *args, **kwargs):
        if path.name.endswith(".backup"):
            raise OSError("simulated cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(official_path), "unlink", fail_backup_cleanup)

    first_paths = save_player_id_snapshots({"afl_official": [player("101")]}, 2026)
    second_paths = save_player_id_snapshots({"afl_official": [player("102")]}, 2026)

    assert first_paths == second_paths
    assert json.loads(official_path.read_text())[0]["id"] == "102"
    backup_paths = [path for path in mapping_dir.iterdir() if path.suffix == ".backup"]
    assert len(backup_paths) == 2
    assert "Could not remove obsolete snapshot file" in caplog.text


def test_promotion_failure_restores_every_previous_snapshot(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    mapping_dir = tmp_path / "data/mapping"
    mapping_dir.mkdir(parents=True)
    official_path = mapping_dir / "2026_afl_official.json"
    tables_path = mapping_dir / "2026_afl_tables.json"
    official_path.write_text("old official")
    tables_path.write_text("old tables")
    real_replace = type(official_path).replace

    def fail_second_temporary_promotion(path, target):
        target = type(path)(target)
        if path.suffix == ".tmp" and target.name == tables_path.name:
            raise OSError("simulated promotion failure")
        return real_replace(path, target)

    monkeypatch.setattr(type(official_path), "replace", fail_second_temporary_promotion)

    with pytest.raises(OSError, match="simulated promotion failure"):
        save_player_id_snapshots(
            {
                "afl_official": [player("101")],
                "afl_tables": [player("Alex_Smith")],
            },
            2026,
        )

    assert official_path.read_text() == "old official"
    assert tables_path.read_text() == "old tables"


def test_rollback_cleanup_failure_does_not_mask_promotion_error_or_skip_restore(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.chdir(tmp_path)
    mapping_dir = tmp_path / "data/mapping"
    mapping_dir.mkdir(parents=True)
    official_path = mapping_dir / "2026_afl_official.json"
    tables_path = mapping_dir / "2026_afl_tables.json"
    official_path.write_text("old official")
    tables_path.write_text("old tables")
    path_type = type(official_path)
    real_replace = path_type.replace
    real_unlink = path_type.unlink

    def fail_second_temporary_promotion(path, target):
        target = path_type(target)
        if path.suffix == ".tmp" and target.name == tables_path.name:
            raise OSError("simulated promotion failure")
        return real_replace(path, target)

    def fail_promoted_snapshot_cleanup(path, *args, **kwargs):
        if path.name == official_path.name:
            raise OSError("simulated rollback cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(path_type, "replace", fail_second_temporary_promotion)
    monkeypatch.setattr(path_type, "unlink", fail_promoted_snapshot_cleanup)

    with pytest.raises(OSError, match="simulated promotion failure"):
        save_player_id_snapshots(
            {
                "afl_official": [player("101")],
                "afl_tables": [player("Alex_Smith")],
            },
            2026,
        )

    assert official_path.read_text() == "old official"
    assert tables_path.read_text() == "old tables"
    assert "Could not remove obsolete snapshot file" in caplog.text


def test_map_scrape_does_not_promote_official_when_tables_scrape_fails(monkeypatch):
    @contextmanager
    def browser_context(_headless):
        yield object()

    save = Mock()

    def scrape(_browser, _year, source):
        if source == "afl_tables":
            raise RuntimeError("AFL Tables unavailable")
        return [player("101")]

    monkeypatch.setattr(cli_module, "sync_browser_context", browser_context)
    monkeypatch.setattr(snapshot_module, "scrape_player_ids", scrape)
    monkeypatch.setattr(snapshot_module, "save_player_id_snapshots", save)

    result = CliRunner().invoke(cli, ["map", "scrape", "--year", "2026"])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    save.assert_not_called()
