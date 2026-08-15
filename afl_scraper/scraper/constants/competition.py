"""Versioned competition rules used to validate historical AFL data."""

from dataclasses import dataclass


MIN_HISTORY_YEAR = 2006
MAX_CONFIGURED_YEAR = 2026

_BASE_TEAMS = (
    "Adelaide",
    "Brisbane Lions",
    "Carlton",
    "Collingwood",
    "Essendon",
    "Fremantle",
    "Geelong",
    "Hawthorn",
    "Melbourne",
    "North Melbourne",
    "Port Adelaide",
    "Richmond",
    "St Kilda",
    "Sydney",
    "West Coast",
    "Western Bulldogs",
)


@dataclass(frozen=True)
class CompetitionRules:
    """Expected source structure for one AFL season."""

    year: int
    teams: tuple[str, ...]
    participating_players_per_team: int
    maximum_published_players_per_team: int


def competition_rules_for_year(year: int) -> CompetitionRules:
    """Return explicit rules for a configured historical season.

    The boundaries deliberately fail closed. A future expansion or rules change
    must be reviewed before new source data is accepted.
    """
    if not MIN_HISTORY_YEAR <= year <= MAX_CONFIGURED_YEAR:
        raise ValueError(
            f"AFL competition validation is configured for "
            f"{MIN_HISTORY_YEAR}-{MAX_CONFIGURED_YEAR}; got {year}"
        )

    teams = list(_BASE_TEAMS)
    if year <= 2007:
        teams[teams.index("North Melbourne")] = "Kangaroos"
    if year >= 2011:
        teams.append("Gold Coast")
    if year >= 2012:
        teams.append("Greater Western Sydney")

    # AFL match-day teams contained 22 named players through 2020. A named
    # medical substitute increased that to 23 in 2021; the current AFL page can
    # additionally publish one wholly zero-stat, non-participating player.
    participants = 22 if year <= 2020 else 23
    maximum_published = 24 if year >= 2026 else participants

    return CompetitionRules(
        year=year,
        teams=tuple(teams),
        participating_players_per_team=participants,
        maximum_published_players_per_team=maximum_published,
    )
