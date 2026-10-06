"""CLI contract for read-only AFL Official season preparation."""

from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from afl_scraper.cli import cli


def test_official_season_cli_reports_dry_run_totals():
    prepared = [
        SimpleNamespace(player_stats=[object(), object()]),
        SimpleNamespace(player_stats=[object(), object(), object()]),
    ]

    with patch(
        "afl_scraper.pipelines.prepare_official_season",
        return_value=prepared,
    ) as prepare:
        result = CliRunner().invoke(cli, ["pipeline", "official-season", "2012"])

    assert result.exit_code == 0, result.output
    assert (
        "Validated 2 official matches and 5 player-stat rows for 2012" in result.output
    )
    assert "Database writes: 0 (dry run)" in result.output
    prepare.assert_called_once_with(2012)


def test_official_season_cli_returns_nonzero_clean_failure():
    with patch(
        "afl_scraper.pipelines.prepare_official_season",
        side_effect=ValueError("missing 1 match caches: 101"),
    ):
        result = CliRunner().invoke(cli, ["pipeline", "official-season", "2012"])

    assert result.exit_code == 1
    assert "Error: missing 1 match caches: 101" in result.output
    assert "Traceback" not in result.output


def test_official_season_cli_requires_integer_year():
    result = CliRunner().invoke(cli, ["pipeline", "official-season", "not-a-year"])

    assert result.exit_code == 2
    assert "Invalid value for 'YEAR'" in result.output
