"""Unit tests for the teams transformation module."""

import pytest
from afl_scraper.transformer.teams import transform_team_name


class TestTransformTeamName:
    """Test cases for the transform_team_name function."""

    def test_transform_full_team_name(self):
        """Test transformation of full team names."""
        assert transform_team_name("adelaide crows") == "Adelaide"
        assert transform_team_name("brisbane lions") == "Brisbane Lions"
        assert transform_team_name("carlton blues") == "Carlton"

    def test_transform_team_nickname(self):
        """Test transformation using team nicknames."""
        assert transform_team_name("crows") == "Adelaide"
        assert transform_team_name("lions") == "Brisbane Lions"
        assert transform_team_name("blues") == "Carlton"
        assert transform_team_name("bombers") == "Essendon"

    def test_transform_short_team_name(self):
        """Test transformation using short team names."""
        assert transform_team_name("adelaide") == "Adelaide"
        assert transform_team_name("collingwood") == "Collingwood"
        assert transform_team_name("richmond") == "Richmond"

    def test_transform_case_insensitive(self):
        """Test that transformation is case insensitive."""
        assert transform_team_name("ADELAIDE") == "Adelaide"
        assert transform_team_name("Adelaide") == "Adelaide"
        assert transform_team_name("AdElAiDe") == "Adelaide"
        assert transform_team_name("CROWS") == "Adelaide"
        assert transform_team_name("Crows") == "Adelaide"

    def test_transform_all_teams(self):
        """Test transformation for all unique team IDs."""
        expected_teams = {
            "Adelaide",
            "Brisbane Lions",
            "Carlton",
            "Essendon",
            "Collingwood",
            "Fremantle",
            "Geelong",
            "Gold Coast",
            "Greater Western Sydney",
            "Hawthorn",
            "Melbourne",
            "North Melbourne",
            "Port Adelaide",
            "Richmond",
            "St Kilda",
            "Sydney",
            "West Coast",
            "Western Bulldogs",
        }

        # Test at least one variant for each team
        test_cases = [
            ("adelaide", "Adelaide"),
            ("brisbane", "Brisbane Lions"),
            ("carlton", "Carlton"),
            ("essendon", "Essendon"),
            ("collingwood", "Collingwood"),
            ("fremantle", "Fremantle"),
            ("geelong", "Geelong"),
            ("gold coast", "Gold Coast"),
            ("gws", "Greater Western Sydney"),
            ("hawthorn", "Hawthorn"),
            ("melbourne", "Melbourne"),
            ("north melbourne", "North Melbourne"),
            ("port adelaide", "Port Adelaide"),
            ("richmond", "Richmond"),
            ("st kilda", "St Kilda"),
            ("sydney", "Sydney"),
            ("west coast", "West Coast"),
            ("western bulldogs", "Western Bulldogs"),
        ]

        for input_name, expected_id in test_cases:
            assert transform_team_name(input_name) == expected_id

    def test_transform_unknown_team_raises_exception(self):
        """Test that an unknown team name raises an exception."""
        with pytest.raises(Exception) as exc_info:
            transform_team_name("unknown team")

        assert "No team ID mapping found for unknown team" in str(exc_info.value)

    def test_transform_empty_string_raises_exception(self):
        """Test that an empty string raises an exception."""
        with pytest.raises(Exception) as exc_info:
            transform_team_name("")

        assert "No team ID mapping found for" in str(exc_info.value)

    def test_transform_nonexistent_team_raises_exception(self):
        """Test that various non-existent teams raise exceptions."""
        invalid_teams = ["hobart", "darwin", "nt thunder", "foobar"]

        for invalid_team in invalid_teams:
            with pytest.raises(Exception) as exc_info:
                transform_team_name(invalid_team)
            assert f"No team ID mapping found for {invalid_team}" in str(exc_info.value)
