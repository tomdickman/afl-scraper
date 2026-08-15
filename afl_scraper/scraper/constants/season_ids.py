"""
Map of competition years to season IDs used on the AFL website.
"""

OFFICIAL_FIXTURE_MIN_YEAR = 2012

# Verified against the public AFL competition-season catalogue on 2026-08-15.
# The official catalogue exposes no AFL Premiership seasons before 2012.
SEASON_ID: dict[int, int] = {
    2026: 85,
    2025: 73,
    2024: 62,
    2023: 52,
    2022: 43,
    2021: 34,
    2020: 20,
    2019: 18,
    2018: 14,
    2017: 11,
    2016: 9,
    2015: 7,
    2014: 5,
    2013: 4,
    2012: 2,
}


def official_season_id(year: int) -> int:
    """Resolve a reviewed AFL fixture season ID with a useful boundary error."""
    try:
        return SEASON_ID[year]
    except KeyError as exc:
        if year < OFFICIAL_FIXTURE_MIN_YEAR:
            raise ValueError(
                "AFL official fixture coverage starts at 2012; "
                f"season {year} requires a historical match source"
            ) from exc
        raise ValueError(
            f"No reviewed AFL official fixture season ID is configured for {year}"
        ) from exc
