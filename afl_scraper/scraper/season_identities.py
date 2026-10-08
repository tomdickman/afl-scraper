"""Historical AFL Official identities derived from completed match pages."""

import re
from collections.abc import Callable

from playwright.sync_api import BrowserContext

from ..models.player import PlayerInfo
from ..utils.identity import normalize_person_name
from .models import RawMatchData, RawPlayerStat, SeasonManifest
from .scrape import load_raw_match_data, scrape_match

ProgressCallback = Callable[[int, int, int, bool], None]

_SAME_SOURCE_GIVEN_NAME_ALIASES = {
    frozenset(("paddy", "patrick")),
}


def _missing_fallback_identity(error: RuntimeError) -> bool:
    """Return whether a wrapped AFL Tables fallback may succeed after seeding IDs."""
    current: BaseException | None = error
    while current is not None:
        if "resolved to 0 official identities" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


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


def _same_source_name(left: str, right: str) -> bool:
    """Accept conservative given-name shortening for one anchored source ID."""
    left_parts = normalize_person_name(left).split()
    right_parts = normalize_person_name(right).split()
    if left_parts == right_parts:
        return True
    if len(left_parts) < 2 or len(right_parts) < 2:
        return False
    if left_parts[1:] != right_parts[1:]:
        return False

    left_given = left_parts[0]
    right_given = right_parts[0]
    if frozenset((left_given, right_given)) in _SAME_SOURCE_GIVEN_NAME_ALIASES:
        return True
    shorter, longer = sorted((left_given, right_given), key=len)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _add_identity(
    identities: dict[str, PlayerInfo],
    player: PlayerInfo,
    match_id: int,
) -> None:
    previous = identities.get(player.id)
    if previous is None:
        identities[player.id] = player
        return

    same_name = _same_source_name(previous.display_name(), player.display_name())
    same_team = " ".join(previous.team.casefold().split()) == " ".join(
        player.team.casefold().split()
    )
    if not same_name or not same_team or previous.year != player.year:
        raise ValueError(
            f"Conflicting AFL official identity {player.id} in match {match_id}: "
            f"{previous.display_name()} ({previous.team}, {previous.year}) vs "
            f"{player.display_name()} ({player.team}, {player.year})"
        )
    if len(normalize_person_name(player.display_name())) > len(
        normalize_person_name(previous.display_name())
    ):
        identities[player.id] = player


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
    cached_matches: dict[int, RawMatchData] = {}
    if not refresh:
        for match_id in manifest.match_ids:
            try:
                raw_match = load_raw_match_data(match_id)
            except FileNotFoundError:
                continue
            collect_match_identities(
                identities,
                raw_match,
                match_id,
                manifest.year,
            )
            cached_matches[match_id] = raw_match

    deferred: list[tuple[int, int, RuntimeError]] = []
    for index, match_id in enumerate(manifest.match_ids, start=1):
        raw_match = cached_matches.get(match_id)
        cached = raw_match is not None
        if raw_match is None:
            try:
                raw_match = scrape_match(
                    browser,
                    match_id,
                    expected_year=manifest.year,
                    fixture=manifest.fixture_for(match_id),
                    player_identities=list(identities.values()),
                )
            except RuntimeError as error:
                if not _missing_fallback_identity(error):
                    raise
                deferred.append((index, match_id, error))
                continue

        collect_match_identities(
            identities,
            raw_match,
            match_id,
            manifest.year,
        )
        if progress is not None:
            progress(index, total, match_id, cached)

    while deferred:
        remaining = []
        completed = 0
        for index, match_id, _previous_error in deferred:
            try:
                raw_match = scrape_match(
                    browser,
                    match_id,
                    expected_year=manifest.year,
                    fixture=manifest.fixture_for(match_id),
                    player_identities=list(identities.values()),
                )
            except RuntimeError as error:
                if not _missing_fallback_identity(error):
                    raise
                remaining.append((index, match_id, error))
                continue
            collect_match_identities(
                identities,
                raw_match,
                match_id,
                manifest.year,
            )
            completed += 1
            if progress is not None:
                progress(index, total, match_id, False)
        if not completed:
            match_ids = ", ".join(str(item[1]) for item in remaining)
            raise RuntimeError(
                f"Could not resolve AFL Official identities for deferred matches "
                f"{match_ids} after scanning every match in {manifest.year}"
            ) from remaining[0][2]
        deferred = remaining

    if not identities:
        raise ValueError(
            f"No participating player identities found for {manifest.year}"
        )
    return sorted(identities.values(), key=lambda player: int(player.id))
