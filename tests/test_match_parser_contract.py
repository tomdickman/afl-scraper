"""Contract tests for the current and legacy AFL player-stat tables."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import afl_scraper.scraper.parser.match as match_parser
from afl_scraper.scraper.constants import competition_rules_for_year
from afl_scraper.scraper.parser.match import (
    OfficialMatchDetailsUnavailable,
    _canonical_fields,
    _extract_match_details,
    _extract_match_year,
    _extract_player_identity,
    _parse_integer,
    _parse_player_stat,
    _player_id_from_href,
    _remove_non_participating_extra,
    _select_team,
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


def test_player_identity_comes_from_semantic_name_element_not_whole_cell():
    row = MagicMock()
    player_link = MagicMock()
    player_name = MagicMock()
    row.locator.return_value = player_link
    player_link.count.return_value = 1
    player_link.locator.return_value = player_name
    player_link.get_attribute.return_value = "/players/1336/jack-scrimshaw"
    player_link.inner_text.return_value = "Jack Scrimshaw Injured"
    player_name.count.return_value = 1
    player_name.inner_text.return_value = "Jack Scrimshaw"

    name, href = _extract_player_identity(row)

    assert name == "Jack Scrimshaw"
    assert href == "/players/1336/jack-scrimshaw"
    row.locator.assert_called_once_with(
        'a.mc-player-stats-table__player[href*="/players/"]'
    )
    player_link.locator.assert_called_once_with(".mc-player-stats-table__name")


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


def test_completely_absent_official_header_has_typed_fallback_signal():
    page = MagicMock()
    page.locator.return_value.count.return_value = 0

    with pytest.raises(OfficialMatchDetailsUnavailable):
        _extract_match_details(page)


def test_missing_date_header_has_typed_fallback_signal():
    page = MagicMock()
    page.locator.return_value.count.return_value = 0

    with pytest.raises(OfficialMatchDetailsUnavailable):
        _extract_match_year(page)


def test_partially_rendered_official_header_refuses_fallback():
    page = MagicMock()

    def locator(selector):
        result = MagicMock()
        result.count.return_value = int(selector == ".mc-header__date-wrapper")
        return result

    page.locator.side_effect = locator

    with pytest.raises(ValueError, match="partially rendered"):
        _extract_match_details(page)


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


def test_metres_gained_accepts_historical_negative_net_values():
    row = _observed_row()
    values = list(row["values"])
    values[row["headers"].index("MG")] = "-14"

    stat = _parse_player_stat(row["headers"], values, row["href"])

    assert stat.metres_gained == -14
    with pytest.raises(ValueError, match="Negative integer value for kicks"):
        _parse_integer("-1", "kicks")


def test_fantasy_points_accept_negative_scores():
    row = _observed_row()
    values = list(row["values"])
    values[row["headers"].index("AF")] = "-1"

    stat = _parse_player_stat(row["headers"], values, row["href"])

    assert stat.fantasy_points == -1


def test_team_option_dispatch_avoids_detached_node_actionability_wait(monkeypatch):
    page = MagicMock()
    table = MagicMock()
    rows = MagicMock()
    previous = [f"/players/{index}" for index in range(100, 122)]
    current = [f"/players/{index}" for index in range(200, 222)]
    rows.evaluate_all.side_effect = [previous, current]
    table.locator.return_value = rows

    selector = MagicMock()
    options = MagicMock()
    first = MagicMock()
    first.inner_text.return_value = "Both"
    options.first = first
    options.count.return_value = 3
    away = MagicMock()
    away.inner_text.return_value = "Collingwood"
    options.nth.return_value = away
    page.locator.side_effect = [selector, options]
    expectation = MagicMock()
    monkeypatch.setattr(match_parser, "expect", lambda _locator: expectation)

    _select_team(page, table, 2, competition_rules_for_year(2013))

    away.dispatch_event.assert_called_once_with("click")
    away.click.assert_not_called()
    expectation.to_contain_text.assert_called_once_with("Collingwood")
    page.wait_for_function.assert_called_once()


@pytest.mark.parametrize(("year", "count"), [(2012, 22), (2021, 23), (2026, 23)])
def test_team_validation_uses_season_roster_rules(year, count):
    row = _observed_row()
    base = _parse_player_stat(row["headers"], row["values"], row["href"])
    home = [
        base.model_copy(update={"afl_official_id": str(1000 + index)})
        for index in range(count)
    ]
    away = [
        base.model_copy(update={"afl_official_id": str(2000 + index)})
        for index in range(count)
    ]
    rules = competition_rules_for_year(year)

    _validate_team_stats(home, away, rules)

    with pytest.raises(ValueError, match="duplicate official IDs"):
        _validate_team_stats(home[:-1] + [home[0]], away, rules)
    with pytest.raises(ValueError, match="both teams"):
        _validate_team_stats(home, away[:-1] + [home[0]], rules)


def test_current_zero_stat_published_extra_is_removed_fail_closed():
    row = _observed_row()
    base = _parse_player_stat(row["headers"], row["values"], row["href"])
    playing = [
        base.model_copy(update={"afl_official_id": str(1000 + index)})
        for index in range(23)
    ]
    zero_values = {
        field: 0
        for field in type(base).model_fields
        if field
        not in {"afl_official_id", "player_name", "jumper_number", "extra_stats"}
    }
    non_participant = type(base).model_validate(
        {**base.model_dump(), "afl_official_id": "9999", **zero_values}
    )
    rules = competition_rules_for_year(2026)

    normalized = _remove_non_participating_extra(
        playing[:8] + [non_participant] + playing[8:], rules
    )

    assert normalized == playing

    all_participating = playing + [base.model_copy(update={"afl_official_id": "9998"})]
    assert len(_remove_non_participating_extra(all_participating, rules)) == 24
    with pytest.raises(ValueError, match="Expected 23 home players"):
        _validate_team_stats(all_participating, playing, rules)
