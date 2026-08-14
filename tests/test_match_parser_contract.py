"""Contract tests for the current and legacy AFL player-stat tables."""

import json
from pathlib import Path

import pytest

from afl_scraper.scraper.parser.match import (
    _canonical_fields,
    _parse_integer,
    _parse_player_stat,
    _player_id_from_href,
    _validate_team_stats,
)


FIXTURE = Path(__file__).parent / "fixtures/afl_match_8224_player_row.json"


def _observed_row():
    return json.loads(FIXTURE.read_text())


def test_current_afl_headers_parse_by_name_not_position():
    row = _observed_row()

    stat = _parse_player_stat(row["headers"], row["values"], row["href"])

    assert stat.afl_official_id == "857"
    assert stat.player_name == "Marcus Bontempelli"
    assert stat.kicks == 12
    assert stat.handballs == 13
    assert stat.disposals == 25
    assert stat.metres_gained == 360
    assert stat.time_on_ground_percent == 86


def test_reordered_columns_produce_the_same_record():
    row = _observed_row()
    order = [1, 0, 14, 12, 9, 6, 7, 5, 2, 3, 4, 8, 10, 11, 13]

    original = _parse_player_stat(row["headers"], row["values"], row["href"])
    reordered = _parse_player_stat(
        [row["headers"][index] for index in order],
        [row["values"][index] for index in order],
        row["href"],
    )

    assert reordered == original


def test_legacy_aliases_remain_supported():
    row = _observed_row()
    headers = [
        "HB" if value == "H" else "CL" if value == "CLR" else value
        for value in row["headers"]
    ]

    stat = _parse_player_stat(headers, row["values"], row["href"])

    assert stat.handballs == 13
    assert stat.clearances == 2


def test_unknown_columns_are_preserved_for_analysis():
    row = _observed_row()

    stat = _parse_player_stat(
        row["headers"] + ["Pressure Acts"],
        row["values"] + ["18"],
        row["href"],
    )

    assert stat.extra_stats == {"Pressure Acts": "18"}


def test_missing_required_column_fails_closed():
    with pytest.raises(ValueError, match="missing required fields"):
        _canonical_fields(["#", "Player", "K"])


def test_invalid_disposal_equation_is_rejected():
    row = _observed_row()
    values = list(row["values"])
    values[row["headers"].index("D")] = "99"

    with pytest.raises(ValueError, match="Disposals do not equal"):
        _parse_player_stat(row["headers"], values, row["href"])


def test_player_ids_are_extracted_without_fixed_length_assumptions():
    assert _player_id_from_href("/players/35/example") == "35"
    assert _player_id_from_href("/players/10256/example") == "10256"
    with pytest.raises(ValueError):
        _player_id_from_href("/players/not-a-number/example")


def test_dash_is_source_normalized_to_zero():
    assert _parse_integer("-", "kicks") == 0


def test_team_validation_requires_23_unique_disjoint_official_ids():
    row = _observed_row()
    base = _parse_player_stat(row["headers"], row["values"], row["href"])
    home = [
        base.model_copy(update={"afl_official_id": str(1000 + index)})
        for index in range(23)
    ]
    away = [
        base.model_copy(update={"afl_official_id": str(2000 + index)})
        for index in range(23)
    ]

    _validate_team_stats(home, away)

    with pytest.raises(ValueError, match="duplicate official IDs"):
        _validate_team_stats(home[:-1] + [home[0]], away)
    with pytest.raises(ValueError, match="both teams"):
        _validate_team_stats(home, away[:-1] + [home[0]])
