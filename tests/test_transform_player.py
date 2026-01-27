"""Unit tests for the player transformation module."""

from datetime import datetime

import pytest

from afl_scraper.models import Player
from afl_scraper.scraper.models import RawPlayer
from afl_scraper.transformer.player import transform_player


class TestTransformPlayer:
    """Test cases for the transform_player function."""

    def test_transform_player_basic(self):
        """Test basic transformation of a player."""
        raw_player = RawPlayer(
            id="CD_I1000001",
            first_name="John",
            last_name="Smith",
            date_of_birth="15-Jan-1990",
        )

        result = transform_player(raw_player)

        assert isinstance(result, Player)
        assert result.id == "CD_I1000001"
        assert result.givenname == "John"
        assert result.familyname == "Smith"
        assert result.birthdate == datetime(1990, 1, 15)

    def test_transform_player_different_names(self):
        """Test transformation with different name combinations."""
        test_cases = [
            ("Marcus", "Bontempelli"),
            ("Patrick", "Dangerfield"),
            ("Lachie", "Neale"),
            ("Christian", "Petracca"),
        ]

        for first_name, last_name in test_cases:
            raw_player = RawPlayer(
                id=f"{first_name[0]}_{last_name[0]}",
                first_name=first_name,
                last_name=last_name,
                date_of_birth="01-Jan-2006",
            )

            result = transform_player(raw_player)

            assert result.givenname == first_name
            assert result.familyname == last_name

    def test_transform_player_different_months(self):
        """Test date parsing with different months."""
        months = [
            ("Jan", 1),
            ("Feb", 2),
            ("Mar", 3),
            ("Apr", 4),
            ("May", 5),
            ("Jun", 6),
            ("Jul", 7),
            ("Aug", 8),
            ("Sep", 9),
            ("Oct", 10),
            ("Nov", 11),
            ("Dec", 12),
        ]

        for month_abbr, month_num in months:
            raw_player = RawPlayer(
                id="John_Smith",
                first_name="Test",
                last_name="Player",
                date_of_birth=f"15-{month_abbr}-2000",
            )

            result = transform_player(raw_player)

            assert result.birthdate.month == month_num
            assert result.birthdate.year == 2000
            assert result.birthdate.day == 15

    def test_transform_player_different_days(self):
        """Test date parsing with different day values."""
        days = [1, 10, 15, 28, 31]

        for day in days:
            raw_player = RawPlayer(
                id="John_Smith",
                first_name="Test",
                last_name="Player",
                date_of_birth=f"{day:02d}-Jan-2000",
            )

            result = transform_player(raw_player)

            assert result.birthdate.day == day

    def test_transform_player_different_years(self):
        """Test date parsing with different year values."""
        years = [1970, 1985, 1990, 1995, 2000, 2005]

        for year in years:
            raw_player = RawPlayer(
                id="John_Smith",
                first_name="Test",
                last_name="Player",
                date_of_birth=f"15-Jan-{year}",
            )

            result = transform_player(raw_player)

            assert result.birthdate.year == year

    def test_transform_player_leap_year(self):
        """Test date parsing with leap year date."""
        raw_player = RawPlayer(
            id="John_Smith",
            first_name="Test",
            last_name="Player",
            date_of_birth="29-Feb-2000",
        )

        result = transform_player(raw_player)

        assert result.birthdate == datetime(2000, 2, 29)

    def test_transform_player_preserves_id(self):
        """Test that player ID is preserved correctly."""
        player_ids = [
            "James_Worpel",
            "Harry_Jones2",
            "Archie_Roberts1",
            "Callum_Ah_Chee",
        ]

        for player_id in player_ids:
            raw_player = RawPlayer(
                id=player_id,
                first_name="Test",
                last_name="Player",
                date_of_birth="01-Jan-1990",
            )

            result = transform_player(raw_player)

            assert result.id == player_id

    def test_transform_player_invalid_date_format_raises_error(self):
        """Test that invalid date format raises ValueError."""
        invalid_dates = [
            "1990-01-15",  # Wrong format (ISO)
            "15/01/1990",  # Wrong separator
            "15-January-1990",  # Full month name
            "15-01-1990",  # Numeric month
            "Jan-15-1990",  # Wrong order
            "invalid",  # Completely invalid
        ]

        for invalid_date in invalid_dates:
            raw_player = RawPlayer(
                id="Levi_Ashcroft",
                first_name="Test",
                last_name="Player",
                date_of_birth=invalid_date,
            )

            with pytest.raises(ValueError):
                transform_player(raw_player)

    def test_transform_player_invalid_leap_year(self):
        """Test that invalid leap year date raises ValueError."""
        # 1999 is not a leap year, so Feb 29 should fail
        raw_player = RawPlayer(
            id="Lance_Franklin",
            first_name="Test",
            last_name="Player",
            date_of_birth="29-Feb-1999",
        )

        with pytest.raises(ValueError):
            transform_player(raw_player)

    def test_transform_player_invalid_day(self):
        """Test that invalid day for month raises ValueError."""
        # April has only 30 days
        raw_player = RawPlayer(
            id="James_Worpel",
            first_name="Test",
            last_name="Player",
            date_of_birth="31-Apr-2000",
        )

        with pytest.raises(ValueError):
            transform_player(raw_player)

    def test_transform_player_real_player_example(self):
        """Test with a realistic player example."""
        raw_player = RawPlayer(
            id="Clayton_Oliver",
            first_name="Clayton",
            last_name="Oliver",
            date_of_birth="22-Jul-1997",
        )

        result = transform_player(raw_player)

        assert result.id == "Clayton_Oliver"
        assert result.givenname == "Clayton"
        assert result.familyname == "Oliver"
        assert result.birthdate == datetime(1997, 7, 22)

    def test_transform_player_special_characters_in_name(self):
        """Test transformation with special characters in names."""
        test_cases = [
            ("Jack", "O'Brien"),
            ("Tom", "McDonald"),
            ("Jean-Luc", "Dupont"),
        ]

        for first_name, last_name in test_cases:
            raw_player = RawPlayer(
                id="Player_Name",
                first_name=first_name,
                last_name=last_name,
                date_of_birth="01-Jan-1995",
            )

            result = transform_player(raw_player)

            assert result.givenname == first_name
            assert result.familyname == last_name
