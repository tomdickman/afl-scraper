"""Historical AFL Official identities derived from completed match pages."""

import re
from collections.abc import Callable

from playwright.sync_api import BrowserContext

from ..models.player import PlayerInfo
from ..utils.identity import normalize_person_name
from .models import RawMatchData, RawPlayerStat, SeasonManifest
from .scrape import load_raw_match_data, scrape_match


ProgressCallback = Callable[[int, int, int, bool], None]


def _player_info(
    stat: RawPlayerStat,
    team: str,
    year: int,
) -> PlayerInfo:
    name_parts = stat.player_name.split(maxsplit=1)
    if len(name_parts) != 2 or not all(name_parts):
        raise ValueError(
            f"AFL official player {stat.afl_official_id} has an incomplete "
            f"name {stat.player_name!r}"
        )
    return PlayerInfo(
        id=stat.afl_official_id,
        first_name=name_parts[0],
        last_name=name_parts[1],
        team=team,
        year=year,
    )


def _match_year(raw_match: RawMatchData) -> int:
    years = re.findall(r"\b(?:19|20)\d{2}\b", raw_match.details.date)
    if len(years) != 1:
        raise ValueError(
            f"Could not parse one match year from {raw_match.details.date!r}"
        )
    return int(years[0])


def _add_identity(
    identities: dict[str, PlayerInfo],
    player: PlayerInfo,
    match_id: int,
) -> None:
    previous = identities.get(player.id)
    if previous is None:
        identities[player.id] = player
        return

    same_name = normalize_person_name(previous.display_name()) == normalize_person_name(
        player.display_name()
    )
    same_team = " ".join(previous.team.casefold().split()) == " ".join(
        player.team.casefold().split()
    )
    if not same_name or not same_team or previous.year != player.year:
        raise ValueError(
            f"Conflicting AFL official identity {player.id} in match {match_id}: "
            f"{previous.display_name()} ({previous.team}, {previous.year}) vs "
            f"{player.display_name()} ({player.team}, {player.year})"
        )


def collect_match_identities(
    identities: dict[str, PlayerInfo],
    raw_match: RawMatchData,
    match_id: int,
    year: int,
) -> None:
    """Add one validated match to a season identity collection."""
    raw_match = RawMatchData.model_validate(raw_match)
    observed_year = _match_year(raw_match)
    if observed_year != year:
        raise ValueError(
            f"AFL match {match_id} belongs to {observed_year}, expected {year}"
        )

    for stat in raw_match.home_team_stats:
        _add_identity(
            identities,
            _player_info(stat, raw_match.details.home_team, year),
            match_id,
        )
    for stat in raw_match.away_team_stats:
        _add_identity(
            identities,
            _player_info(stat, raw_match.details.away_team, year),
            match_id,
        )


def scrape_season_player_ids(
    browser: BrowserContext,
    manifest: SeasonManifest,
    *,
    refresh: bool = False,
    progress: ProgressCallback | None = None,
) -> list[PlayerInfo]:
    """Collect every participating official identity in a completed season.

    Validated match JSON is reused by default. A malformed cache is not silently
    replaced; callers must deliberately pass ``refresh=True`` to reacquire it.
    """
    identities: dict[str, PlayerInfo] = {}
    total = manifest.match_count
    for index, match_id in enumerate(manifest.match_ids, start=1):
        cached = False
        if refresh:
            raw_match = scrape_match(browser, match_id)
        else:
            try:
                raw_match = load_raw_match_data(match_id)
                cached = True
            except FileNotFoundError:
                raw_match = scrape_match(browser, match_id)

        collect_match_identities(
            identities,
            raw_match,
            match_id,
            manifest.year,
        )
        if progress is not None:
            progress(index, total, match_id, cached)

    if not identities:
        raise ValueError(
            f"No participating player identities found for {manifest.year}"
        )
    return sorted(identities.values(), key=lambda player: int(player.id))
