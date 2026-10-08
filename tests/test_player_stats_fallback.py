from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest

from afl_scraper.models import PlayerInfo
from afl_scraper.scraper import player_stats_fallback
from afl_scraper.scraper.models import (
    MatchMetadataCatalog,
    MatchMetadataRecord,
    RawMatchDetails,
)
from afl_scraper.scraper.player_stats_fallback import parse_afl_tables_player_stats

HEADERS = (
    "#",
    "Player",
    "KI",
    "MK",
    "HB",
    "DI",
    "GL",
    "BH",
    "HO",
    "TK",
    "RB",
    "IF",
    "CL",
    "CG",
    "FF",
    "FA",
    "BR",
    "CP",
    "UP",
    "CM",
    "MI",
    "1%",
    "BO",
    "GA",
    "%P",
)


def _table(team, player, player_id, values):
    headers = "".join(f"<th>{header}</th>" for header in HEADERS)
    cells = "".join(f"<td>{value}</td>" for value in values)
    cells = cells.replace(
        f"<td>{player}</td>",
        f'<td><a href="../../players/P/{player_id}.html">{player}</a></td>',
    )
    return f"""
      <table>
        <thead>
          <tr><th colspan="25">{team} Match Statistics</th></tr>
          <tr>{headers}</tr>
        </thead>
        <tbody><tr>{cells}</tr></tbody>
      </table>
    """


def _html():
    return _table(
        "Port Adelaide",
        "Cassisi, Domenic",
        "Domenic_Cassisi",
        (
            "25 ↓",
            "Cassisi, Domenic",
            1,
            0,
            3,
            4,
            0,
            0,
            0,
            1,
            0,
            0,
            1,
            1,
            0,
            1,
            0,
            1,
            3,
            0,
            0,
            0,
            0,
            0,
            20,
        ),
    ) + _table(
        "Collingwood",
        "Ball, Luke",
        "Luke_Ball",
        (
            12,
            "Ball, Luke",
            9,
            2,
            14,
            23,
            0,
            0,
            0,
            8,
            1,
            2,
            6,
            2,
            1,
            1,
            0,
            10,
            12,
            0,
            0,
            1,
            0,
            0,
            76,
        ),
    )


def _record():
    return MatchMetadataRecord(
        source_match_id="041320130629",
        source_url="https://afltables.com/afl/stats/games/2013/041320130629.html",
        year=2013,
        round="Round 14",
        home_team="Port Adelaide",
        away_team="Collingwood",
        local_date=date(2013, 6, 29),
        local_time=time(16, 10),
        venue="Football Park",
        home_goals=13,
        home_behinds=8,
        home_total=86,
        away_goals=7,
        away_behinds=9,
        away_total=51,
    )


def _details():
    return RawMatchDetails(
        home_team="Port Adelaide",
        away_team="Collingwood",
        round="14",
        date="Saturday 29 June 2013",
        time="4:10 PM (GMT+09:30)",
        venue="AAMI Stadium, Adelaide",
        status="FULL TIME",
        home_team_goals=13,
        home_team_behinds=8,
        home_team_total=86,
        away_team_goals=7,
        away_team_behinds=9,
        away_team_total=51,
    )


def _identities():
    return [
        PlayerInfo(
            id="481",
            firstName="Dom",
            lastName="Cassisi",
            team="Port Adelaide",
            year=2013,
        ),
        PlayerInfo(
            id="549",
            firstName="Luke",
            lastName="Ball",
            team="Collingwood",
            year=2013,
        ),
    ]


def test_match_394_fallback_normalizes_stats_and_preserves_official_ids():
    result = parse_afl_tables_player_stats(
        _html(), _record(), _details(), _identities(), expected_players=1
    )

    home = result.home_team_stats[0]
    away = result.away_team_stats[0]
    assert (home.afl_official_id, home.player_name, home.jumper_number) == (
        "481",
        "Domenic Cassisi",
        25,
    )
    assert home.fantasy_points == 10
    assert home.metres_gained is None
    assert (away.afl_official_id, away.fantasy_points) == ("549", 91)


def test_fallback_fails_closed_when_an_official_identity_is_unavailable():
    with pytest.raises(ValueError, match="resolved to 0 official identities"):
        parse_afl_tables_player_stats(
            _html(), _record(), _details(), _identities()[1:], expected_players=1
        )


def test_fallback_rejects_incomplete_source_headers():
    with pytest.raises(ValueError, match=r"missing fields: \['%P'\]"):
        parse_afl_tables_player_stats(
            _html().replace("<th>%P</th>", ""),
            _record(),
            _details(),
            _identities(),
            expected_players=1,
        )


def test_complete_season_cache_revalidates_cached_afl_tables_pages(
    monkeypatch, tmp_path
):
    catalog = MatchMetadataCatalog(
        year=2013,
        source_url="https://afltables.com/afl/seas/2013.html",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        matches=[_record()],
    )
    fetches = []
    monkeypatch.setattr(
        player_stats_fallback,
        "competition_rules_for_year",
        lambda _year: SimpleNamespace(participating_players_per_team=1),
    )
    monkeypatch.setattr(
        player_stats_fallback,
        "fetch_afl_tables_player_stats",
        lambda _browser, record: fetches.append(record.source_match_id) or _html(),
    )

    first = player_stats_fallback.cache_afl_tables_season_matches(
        object(), catalog, delay_ms=0, raw_root=tmp_path
    )
    second = player_stats_fallback.cache_afl_tables_season_matches(
        object(), catalog, delay_ms=0, raw_root=tmp_path
    )

    expected_path = tmp_path / "041320130629" / "match.html"
    assert first == second == [expected_path]
    assert fetches == ["041320130629"]
    assert expected_path.exists()


def test_source_native_validation_accepts_heading_navigation_links():
    html = _html().replace(
        "Port Adelaide Match Statistics",
        'Port Adelaide Match Statistics [<a href="../../2013.html">Season</a>]',
    )

    assert (
        player_stats_fallback.validate_afl_tables_player_stats_html(
            html, _record(), expected_players=1
        )
        == 2
    )
