"""Unit tests for the match transformation module."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from afl_scraper.scraper.models import RawMatchData, RawMatchDetails, RawPlayerStat
from afl_scraper.transform.match import (
    parse_match_datetime,
    resolve_team,
    resolve_venue,
    transform_match,
)


def _stat(official_id: str, name: str, **overrides) -> RawPlayerStat:
    values = {
        "afl_official_id": official_id,
        "player_name": name,
        "jumper_number": 5,
        "kicks": 12,
        "handballs": 8,
        "disposals": 20,
        "marks": 6,
        "goals": 2,
        "behinds": 1,
        "hitouts": 10,
        "tackles": 4,
        "clearances": 4,
        "metres_gained": 321,
        "goal_assists": 1,
        "time_on_ground_percent": Decimal("85"),
        "fantasy_points": 95,
    }
    values.update(overrides)
    return RawPlayerStat(**values)


def _raw_match() -> RawMatchData:
    return RawMatchData(
        details=RawMatchDetails(
            home_team="Carlton",
            away_team="Collingwood",
            round="Round 1",
            date="Saturday 21 September 2024",
            time="7:30 PM (GMT+10)",
            venue="MCG, Melbourne",
            status="FULL TIME",
            home_team_goals=12,
            home_team_behinds=10,
            home_team_total=82,
            away_team_goals=15,
            away_team_behinds=8,
            away_team_total=98,
        ),
        home_team_stats=[_stat("101", "Player A")],
        away_team_stats=[_stat("102", "Player B", kicks=8, handballs=12)],
    )


class TestResolveVenue:
    def test_exact_and_city_suffix(self):
        assert resolve_venue("MCG", "afl_official") == "M.C.G."
        assert resolve_venue("Marvel Stadium, Melbourne", "afl_official") == "Docklands"

    def test_case_and_whitespace_insensitive(self):
        assert resolve_venue(" marvel   stadium ", "afl_official") == "Docklands"

    def test_unknown_venue_raises(self):
        with pytest.raises(KeyError):
            resolve_venue("Nonexistent Stadium", "afl_official")

    def test_afl_tables_source(self):
        assert resolve_venue("M.C.G.", "afl_tables") == "M.C.G."

    @pytest.mark.parametrize(
        ("source_name", "venue_id"),
        [
            ("Carrara Stadium", "Carrara"),
            ("Marrara Stadium", "Marrara Oval"),
        ],
    )
    def test_australian_football_historical_aliases(self, source_name, venue_id):
        assert resolve_venue(source_name, "australian_football") == venue_id


class TestResolveTeam:
    def test_full_name_nickname_and_case(self):
        assert resolve_team("adelaide crows") == "Adelaide"
        assert resolve_team("Crows") == "Adelaide"
        assert resolve_team("COLLINGWOOD") == "Collingwood"


class TestParseMatchDatetime:
    def test_current_full_date_and_numeric_offset(self):
        dt = parse_match_datetime("Thursday 6 August 2026", "7:30 PM (GMT+10)")
        assert dt == datetime(2026, 8, 6, 19, 30, tzinfo=timezone(timedelta(hours=10)))

    def test_abbreviated_date_and_half_hour_offset(self):
        dt = parse_match_datetime("Sat 21 Sep 2024", "19:30 (GMT+09:30)")
        assert dt.utcoffset() == timedelta(hours=9, minutes=30)
        assert dt.hour == 19

    def test_missing_offset_fails_closed(self):
        with pytest.raises(ValueError, match="numeric GMT offset"):
            parse_match_datetime("Sat 21 Sep 2024", "7:30 PM")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_match_datetime("not a date", "not a time")


class TestTransformMatch:
    def test_basic_transform_uses_official_id_resolver(self):
        calls = []

        def resolve(stat, team, year):
            calls.append((stat.afl_official_id, team, year))
            return {"101": "player_a_01", "102": "player_b_02"}.get(
                stat.afl_official_id
            )

        game, stats = transform_match(_raw_match(), 12345, resolve_player_id=resolve)

        assert game.id == 12345
        assert game.venue == "M.C.G."
        assert game.start_date.utcoffset() == timedelta(hours=10)
        assert game.home_team == "Carlton"
        assert game.away_team == "Collingwood"
        assert game.home_goals == 12
        assert len(stats) == 2
        assert calls == [
            ("101", "Carlton", 2024),
            ("102", "Collingwood", 2024),
        ]

        home = stats[0]
        assert home.player_id == "player_a_01"
        assert home.kicks == 12
        assert home.handballs == 8
        assert home.rebound_50s is None
        assert home.time_on_ground_percent == Decimal("85")
        assert home.fantasy_points == 95

    def test_missing_mapping_fails_instead_of_guessing_by_name(self):
        with pytest.raises(ValueError, match="AFL official ID 101"):
            transform_match(
                _raw_match(),
                12345,
                resolve_player_id=lambda _stat, _team, _year: None,
            )

    def test_typed_record_has_dataframe_analysis_views(self):
        raw = _raw_match()

        frame = raw.home_stats_dataframe()

        assert list(frame["afl_official_id"]) == ["101"]
        assert list(frame["player_name"]) == ["Player A"]
        assert frame.loc[0, "kicks"] == 12
