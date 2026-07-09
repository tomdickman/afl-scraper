"""Unit tests for the match transformation module."""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from afl_scraper.transform.match import (
    parse_match_datetime,
    resolve_team,
    resolve_venue,
    transform_match,
)


class TestResolveVenue:
    def test_exact_match(self):
        assert resolve_venue("MCG", "afl_official") == "M.C.G."
        assert resolve_venue("Marvel Stadium", "afl_official") == "Docklands"
        assert resolve_venue("Gabba", "afl_official") == "Gabba"

    def test_case_insensitive(self):
        assert resolve_venue("mcg", "afl_official") == "M.C.G."
        assert resolve_venue("marvel stadium", "afl_official") == "Docklands"

    def test_whitespace_collapsed(self):
        assert resolve_venue("MCG", "afl_official") == "M.C.G."
        assert resolve_venue("SCG", "afl_official") == "S.C.G."

    def test_unknown_venue_raises(self):
        with pytest.raises(KeyError):
            resolve_venue("Nonexistent Stadium", "afl_official")

    def test_afl_tables_source(self):
        assert resolve_venue("M.C.G.", "afl_tables") == "M.C.G."
        assert resolve_venue("S.C.G.", "afl_tables") == "S.C.G."


class TestResolveTeam:
    def test_full_name(self):
        assert resolve_team("adelaide crows") == "Adelaide"
        assert resolve_team("brisbane lions") == "Brisbane Lions"

    def test_nickname(self):
        assert resolve_team("crows") == "Adelaide"
        assert resolve_team("lions") == "Brisbane Lions"

    def test_short_name(self):
        assert resolve_team("adelaide") == "Adelaide"
        assert resolve_team("collingwood") == "Collingwood"

    def test_case_insensitive(self):
        assert resolve_team("ADELAIDE") == "Adelaide"
        assert resolve_team("Crows") == "Adelaide"


class TestParseMatchDatetime:
    def test_with_day_and_12hr_time(self):
        dt = parse_match_datetime("Sat 21 Sep 2024", "7:30PM")
        assert dt == datetime(2024, 9, 21, 19, 30)

    def test_with_day_and_24hr_time(self):
        dt = parse_match_datetime("Sat 21 Sep 2024", "19:30")
        assert dt == datetime(2024, 9, 21, 19, 30)

    def test_without_day_and_12hr_time(self):
        dt = parse_match_datetime("21 Sep 2024", "7:30PM")
        assert dt == datetime(2024, 9, 21, 19, 30)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_match_datetime("not a date", "not a time")


class TestTransformMatch:
    def test_basic_transform(self):
        raw_data = {
            "details": {
                "home_team": "Carlton",
                "away_team": "Collingwood",
                "round": "Round 1",
                "date": "Sat 21 Sep 2024",
                "time": "7:30PM",
                "venue": "MCG",
                "home_team_goals": 12,
                "home_team_behinds": 10,
                "home_team_total": 82,
                "away_team_goals": 15,
                "away_team_behinds": 8,
                "away_team_total": 98,
            },
            "home_team_stats": pd.DataFrame(
                [["Player A", "5", 12, 8, 6, 2, 1, 10, 4, 3, 5, 4, 2, 1, 0, 8, 10, 1, 1, 3, 0, 1, "85%", 95]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
            "away_team_stats": pd.DataFrame(
                [["Player B", "10", 8, 12, 4, 1, 2, 0, 6, 2, 7, 5, 3, 2, 1, 6, 14, 0, 2, 5, 1, 0, "78%", 72]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
        }

        def mock_resolve(name, team):
            lookup = {"Player A": "player_a_01", "Player B": "player_b_02"}
            return lookup.get(name)

        game, stats = transform_match(raw_data, 12345, resolve_player_id=mock_resolve)

        assert game.id == 12345
        assert game.venue == "M.C.G."
        assert game.round == "Round 1"
        assert game.home_team == "Carlton"
        assert game.away_team == "Collingwood"
        assert game.home_goals == 12
        assert game.away_behinds == 8

        assert len(stats) == 2

        home_pgs = stats[0]
        assert home_pgs.player_id == "player_a_01"
        assert home_pgs.team == "Carlton"
        assert home_pgs.game_id == 12345
        assert home_pgs.kicks == 12
        assert home_pgs.handballs == 8
        assert home_pgs.marks == 6
        assert home_pgs.goals == 2
        assert home_pgs.behinds == 1
        assert home_pgs.hitouts == 10
        assert home_pgs.tackles == 4
        assert home_pgs.rebound_50s == 3
        assert home_pgs.inside_50s == 5
        assert home_pgs.clearances == 4
        assert home_pgs.clangers == 2
        assert home_pgs.free_kicks_for == 1
        assert home_pgs.free_kicks_against == 0
        assert home_pgs.contested_possessions == 8
        assert home_pgs.uncontested_possessions == 10
        assert home_pgs.contested_marks == 1
        assert home_pgs.marks_inside_50 == 1
        assert home_pgs.one_percenters == 3
        assert home_pgs.bounces == 0
        assert home_pgs.goal_assists == 1
        assert home_pgs.time_on_ground_percent == Decimal("85")
        assert home_pgs.fantasy_points == 95
        assert home_pgs.jumper_number == 5
        assert home_pgs.player_game_number == 1

        away_pgs = stats[1]
        assert away_pgs.player_id == "player_b_02"
        assert away_pgs.team == "Collingwood"
        assert away_pgs.player_game_number == 1
        assert away_pgs.kicks == 8
        assert away_pgs.handballs == 12

    def test_empty_player_name_skipped(self):
        raw_data = {
            "details": {
                "home_team": "Carlton",
                "away_team": "Collingwood",
                "round": "Round 1",
                "date": "Sat 21 Sep 2024",
                "time": "7:30PM",
                "venue": "MCG",
                "home_team_goals": 10,
                "home_team_behinds": 10,
                "home_team_total": 70,
                "away_team_goals": 12,
                "away_team_behinds": 8,
                "away_team_total": 80,
            },
            "home_team_stats": pd.DataFrame(
                [["", "5", 12, 8, 6, 2, 1, 10, 4, 3, 5, 4, 2, 1, 0, 8, 10, 1, 1, 3, 0, 1, "85%", 95]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
            "away_team_stats": pd.DataFrame(
                [["Player B", "10", 8, 12, 4, 1, 2, 0, 6, 2, 7, 5, 3, 2, 1, 6, 14, 0, 2, 5, 1, 0, "78%", 72]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
        }

        game, stats = transform_match(raw_data, 12346, resolve_player_id=lambda n, t: n if n else None)

        assert len(stats) == 1
        assert stats[0].player_id == "Player B"

    def test_dashes_handled_as_zero(self):
        raw_data = {
            "details": {
                "home_team": "Carlton",
                "away_team": "Collingwood",
                "round": "Round 1",
                "date": "Sat 21 Sep 2024",
                "time": "7:30PM",
                "venue": "MCG",
                "home_team_goals": 10,
                "home_team_behinds": 10,
                "home_team_total": 70,
                "away_team_goals": 12,
                "away_team_behinds": 8,
                "away_team_total": 80,
            },
            "home_team_stats": pd.DataFrame(
                [["Player A", "5", "-", 8, "-", 0, 1, 10, 4, 3, 5, 4, 2, 1, 0, 8, 10, 1, 1, 3, 0, 1, "85%", 95]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
            "away_team_stats": pd.DataFrame(
                [["Player B", "10", 8, 12, 4, 1, 2, 0, 6, 2, 7, 5, 3, 2, 1, 6, 14, 0, 2, 5, 1, 0, "78%", 72]],
                columns=["Player", "#", "K", "HB", "M", "G", "B", "HO", "T", "R50", "I50", "CL", "CG", "FF", "FA", "CP", "UP", "CM", "MI5", "1%", "BO", "GA", "TOG%", "AF"],
            ),
        }

        game, stats = transform_match(raw_data, 12347, resolve_player_id=lambda n, t: n)

        home_pgs = stats[0]
        assert home_pgs.kicks == 0
        assert home_pgs.handballs == 8
        assert home_pgs.marks == 0
