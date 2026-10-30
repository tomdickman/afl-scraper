"""Contracts for packaged configuration and overridable artifact paths."""

from afl_scraper.config import load_config, load_jsonc_path
from afl_scraper.paths import data_path


def test_packaged_configuration_is_available_outside_repository_paths():
    mappings = load_config("venue_name_mappings.jsonc")

    assert mappings["afl_official"]["MCG"] == "M.C.G."


def test_jsonc_loader_preserves_comment_markers_inside_strings(tmp_path):
    path = tmp_path / "sample.jsonc"
    path.write_text(
        '{\n  // evidence URL\n  "url": "https://example.test/evidence"\n}\n',
        encoding="utf-8",
    )

    assert load_jsonc_path(path) == {"url": "https://example.test/evidence"}


def test_data_root_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("AFL_SCRAPER_DATA_DIR", str(tmp_path))

    assert data_path("raw", "source") == tmp_path / "raw" / "source"
