import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import tempfile
from typing import List
from urllib.parse import urljoin
from uuid import uuid4

from playwright.sync_api import BrowserContext, Locator

from ..models.player import PlayerInfo
from .constants import FIXTURE_CLASSNAMES, PATHS, official_season_id
from .fixture import (
    get_fixture_page,
    get_fixture_url,
    get_round_buttons,
    navigate_to_round,
)
from .models import (
    CachedRawMatch,
    DiscoveredRound,
    MatchDataProvenance,
    OfficialFixtureMetadata,
    RawMatchData,
    SeasonManifest,
)
from .parser import (
    OfficialMatchDetailsUnavailable,
    OfficialPlayerStatsUnavailable,
    display_player_stats,
    extract_table_data,
    select_team_stats,
)
from .sources import PlayerSourceFactory


logger = logging.getLogger(__name__)

_FIXTURE_TIMEZONES = {
    "AEST": timezone(timedelta(hours=10)),
    "AEDT": timezone(timedelta(hours=11)),
    "ACST": timezone(timedelta(hours=9, minutes=30)),
    "ACDT": timezone(timedelta(hours=10, minutes=30)),
    "AWST": timezone(timedelta(hours=8)),
    "NZST": timezone(timedelta(hours=12)),
    "NZDT": timezone(timedelta(hours=13)),
}
_FIXTURE_DATETIME_PATTERN = re.compile(
    r"^(?P<weekday>[A-Za-z]+),\s+(?P<month>[A-Za-z]+)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)\s+(?P<year>\d{4}),\s+"
    r"(?P<clock>\d{1,2}:\d{2}\s+[ap]m)\s+(?P<timezone>[A-Z]{3,4})$",
    re.IGNORECASE,
)


def _remove_directory_best_effort(path: Path) -> None:
    """Remove obsolete scrape data without changing the scrape outcome."""
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("Could not remove obsolete scrape directory %s: %s", path, exc)


def _normalise_match_id(match_id: int | str) -> int:
    """Return a validated numeric AFL match ID."""
    try:
        normalised = int(match_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid AFL match ID: {match_id!r}") from exc

    if normalised <= 0 or str(match_id).strip() != str(normalised):
        raise ValueError(f"Invalid AFL match ID: {match_id!r}")

    return normalised


def _parse_fixture_datetime(value: str) -> datetime | None:
    match = _FIXTURE_DATETIME_PATTERN.fullmatch(" ".join(value.split()))
    if match is None:
        return None
    timezone_name = match.group("timezone").upper()
    offset = _FIXTURE_TIMEZONES.get(timezone_name)
    if offset is None:
        return None
    date_time = (
        f"{match.group('day')} {match.group('month')} "
        f"{match.group('year')} {match.group('clock')}"
    )
    parsed = None
    for month_format in ("%B", "%b"):
        try:
            parsed = datetime.strptime(date_time, f"%d {month_format} %Y %I:%M %p")
        except ValueError:
            continue
        break
    if parsed is None:
        return None
    weekday = match.group("weekday").casefold()
    if weekday not in {
        parsed.strftime("%A").casefold(),
        parsed.strftime("%a").casefold(),
    }:
        return None
    return parsed.replace(tzinfo=offset)


def _fixture_metadata(match: Locator, round_label: str) -> OfficialFixtureMetadata:
    match_id = _normalise_match_id(match.get_attribute("data-match-id"))
    link = match.locator("a.fixtures__absolute-link")
    if link.count() != 1:
        raise ValueError(f"Fixture match {match_id} has no unique semantic link")
    href = link.get_attribute("href")
    if not href:
        raise ValueError(f"Fixture match {match_id} has no source URL")

    def one_text(selector: str, field: str) -> str:
        locator = match.locator(selector)
        if locator.count() != 1:
            raise ValueError(f"Fixture match {match_id} has no unique {field}")
        value = " ".join(locator.inner_text().split())
        if not value:
            raise ValueError(f"Fixture match {match_id} has a blank {field}")
        return value

    home_team = one_text(
        ".fixtures__match-team--home .fixtures__match-team-name", "home team"
    )
    away_team = one_text(
        ".fixtures__match-team--away .fixtures__match-team-name", "away team"
    )
    venue_locator = match.locator(".fixtures__match-venue")
    venue = (
        " ".join(venue_locator.inner_text().split()).rstrip(",")
        if venue_locator.count() == 1
        else None
    )
    totals = [
        " ".join(value.split())
        for value in match.locator(".fixtures__match-score-total").all_inner_texts()
    ]
    home_total = away_total = None
    if len(totals) == 2 and all(value.isdigit() for value in totals):
        home_total, away_total = map(int, totals)

    aria_label = link.get_attribute("aria-label") or ""
    parts = [" ".join(part.split()) for part in aria_label.split(";")]
    scheduled_at = next(
        (
            parsed
            for part in parts
            if (parsed := _parse_fixture_datetime(part)) is not None
        ),
        None,
    )
    explicit_status = match.get_attribute("data-match-status")
    status = (
        explicit_status.upper()
        if explicit_status
        else (
            "COMPLETED"
            if len(totals) == 2 or "final score" in aria_label.casefold()
            else "UNKNOWN"
        )
    )
    return OfficialFixtureMetadata(
        match_id=match_id,
        provider_id=match.get_attribute("data-match-provider-id"),
        round=round_label,
        home_team=home_team,
        away_team=away_team,
        scheduled_at=scheduled_at,
        venue=venue,
        home_total=home_total,
        away_total=away_total,
        status=status,
        source_url=urljoin(PATHS["MATCH"], href),
    )


def _save_raw_html(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    if path.stat().st_size == 0:
        raise ValueError(f"Raw page was empty: {path}")


def scrape_match_ids(
    browser: BrowserContext, round_number: str, year: int | None = None
) -> list[int]:
    page = get_fixture_page(browser, year)
    try:
        navigate_to_round(page, str(round_number))
        matches_locator = page.locator(
            f'{FIXTURE_CLASSNAMES["MATCHES"]}[data-match-id]'
        )
        raw_ids = [
            match_locator.get_attribute("data-match-id")
            for match_locator in matches_locator.all()
        ]
        if not raw_ids:
            raise RuntimeError(f"No matches found for round {round_number!r}")
        return [_normalise_match_id(match_id) for match_id in raw_ids]
    finally:
        page.close()


def discover_official_season(browser: BrowserContext, year: int) -> SeasonManifest:
    """Discover and validate every round and match ID in an AFL season."""
    page = get_fixture_page(browser, year)
    try:
        round_labels = list(get_round_buttons(page))
        if not round_labels:
            raise RuntimeError(f"No rounds found for AFL season {year}")

        rounds = []
        fixtures = []
        for label in round_labels:
            navigate_to_round(page, label)
            matches = page.locator(f'{FIXTURE_CLASSNAMES["MATCHES"]}[data-match-id]')
            match_ids = [
                _normalise_match_id(match.get_attribute("data-match-id"))
                for match in matches.all()
            ]
            if not match_ids:
                raise RuntimeError(
                    f"No matches found for round {label!r} in AFL season {year}"
                )
            rounds.append(DiscoveredRound(label=label, match_ids=match_ids))
            if all(hasattr(match, "locator") for match in matches.all()):
                fixtures.extend(
                    _fixture_metadata(match, label) for match in matches.all()
                )

        return SeasonManifest(
            schema_version=2 if fixtures else 1,
            year=year,
            season_id=official_season_id(year),
            fixture_url=get_fixture_url(year),
            discovered_at=datetime.now(timezone.utc),
            rounds=rounds,
            fixtures=fixtures,
        )
    finally:
        page.close()


def save_season_manifest(
    manifest: SeasonManifest,
    output_root: Path = Path("data/raw/afl_official/season"),
) -> Path:
    """Atomically save a year-scoped, validated season manifest."""
    output_dir = output_root / str(manifest.year)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    temporary_path = output_dir / f".manifest-{uuid4().hex}.tmp"
    try:
        temporary_path.write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


def load_season_manifest(
    year: int,
    input_root: Path = Path("data/raw/afl_official/season"),
) -> SeasonManifest:
    """Load and revalidate a previously discovered official season."""
    path = input_root / str(year) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Season manifest not found: {path}. Run `scrape season {year}` first."
        )
    manifest = SeasonManifest.model_validate_json(path.read_text(encoding="utf-8"))
    if manifest.year != year:
        raise ValueError(
            f"Season manifest at {path} contains year {manifest.year}, expected {year}"
        )
    return manifest


def raw_match_data_path(
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> Path:
    """Return the canonical validated JSON path for an official match."""
    return raw_root / str(_normalise_match_id(match_id)) / "match.json"


def save_raw_match_data(
    raw_data: RawMatchData,
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
    *,
    provenance: MatchDataProvenance | None = None,
) -> Path:
    """Atomically persist one fully validated raw match for safe reuse."""
    raw_match = RawMatchData.model_validate(raw_data)
    normalized_match_id = _normalise_match_id(match_id)
    path = raw_match_data_path(normalized_match_id, raw_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".match-{uuid4().hex}.tmp"
    cached_match = CachedRawMatch(
        schema_version=2 if provenance is not None else 1,
        match_id=normalized_match_id,
        source_url=f"{PATHS['MATCH'].rstrip('/')}/{normalized_match_id}",
        scraped_at=datetime.now(timezone.utc),
        data=raw_match,
        provenance=provenance,
    )
    try:
        temporary_path.write_text(
            cached_match.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


def load_raw_match_data(
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> RawMatchData:
    """Load and revalidate a cached official match."""
    normalized_match_id = _normalise_match_id(match_id)
    path = raw_match_data_path(normalized_match_id, raw_root)
    if not path.exists():
        raise FileNotFoundError(f"Validated raw match not found: {path}")
    cached_match = CachedRawMatch.model_validate_json(path.read_text(encoding="utf-8"))
    if cached_match.match_id != normalized_match_id:
        raise ValueError(
            f"Raw match cache at {path} contains match {cached_match.match_id}, "
            f"expected {normalized_match_id}"
        )
    return cached_match.data


def _scrape_match_player_stats_fallback(
    browser: BrowserContext,
    match_id: int,
    expected_year: int | None,
    fixture: OfficialFixtureMetadata | None,
    player_identities: list[PlayerInfo] | None,
    error: OfficialPlayerStatsUnavailable,
) -> RawMatchData:
    if expected_year is None:
        raise ValueError(
            f"AFL match {match_id} has no official player statistics; "
            "provide its season year for the AFL Tables fallback"
        ) from error
    if not player_identities:
        raise ValueError(
            f"AFL match {match_id} has no official player statistics and "
            "no prior official season identities are available"
        ) from error

    from .constants import competition_rules_for_year
    from .match_metadata import get_match_metadata_catalog
    from .metadata_fallback import (
        match_details_from_record,
        resolve_fallback_match_record,
    )
    from .player_stats_fallback import (
        fetch_afl_tables_player_stats,
        parse_afl_tables_player_stats,
        save_afl_tables_match_html,
    )

    catalog = get_match_metadata_catalog(browser, expected_year)
    record = resolve_fallback_match_record(fixture, catalog)
    assert fixture is not None
    details = match_details_from_record(fixture, record)
    fallback_html = fetch_afl_tables_player_stats(browser, record)
    raw_data = parse_afl_tables_player_stats(
        fallback_html,
        record,
        details,
        list(player_identities),
        expected_players=competition_rules_for_year(
            expected_year
        ).participating_players_per_team,
    )
    save_afl_tables_match_html(fallback_html, record)
    provenance = MatchDataProvenance(
        player_stats_source="afl_tables",
        player_stats_url=record.source_url,
        match_details_source="afl_tables",
        match_details_url=record.source_url,
        official_fixture_url=fixture.source_url,
        cross_checked_fields=(
            "year",
            "round",
            "home_team",
            "away_team",
            "scheduled_at",
            "venue",
            "home_total",
            "away_total",
        ),
        fallback_reason=str(error),
    )
    save_raw_match_data(raw_data, match_id, provenance=provenance)
    return raw_data


def scrape_match(
    browser: BrowserContext,
    match_id: int | str,
    *,
    expected_year: int | None = None,
    fixture: OfficialFixtureMetadata | None = None,
    player_identities: list[PlayerInfo] | None = None,
):
    match_id = _normalise_match_id(match_id)
    page = browser.new_page()
    url = f"{PATHS['MATCH'].rstrip('/')}/{match_id}"
    try:
        page.goto(url)
        try:
            display_player_stats(page)
        except OfficialPlayerStatsUnavailable as error:
            return _scrape_match_player_stats_fallback(
                browser,
                match_id,
                expected_year,
                fixture,
                player_identities,
                error,
            )

        raw_dir = Path("data/raw/afl_official/match") / str(match_id)

        try:
            if expected_year is None:
                select_team_stats(page, 1)
            else:
                select_team_stats(page, 1, expected_year)
            _save_raw_html(raw_dir / "home_player_stats.html", page.content())

            if expected_year is None:
                select_team_stats(page, 2)
            else:
                select_team_stats(page, 2, expected_year)
            _save_raw_html(raw_dir / "away_player_stats.html", page.content())
        except OfficialPlayerStatsUnavailable as error:
            return _scrape_match_player_stats_fallback(
                browser,
                match_id,
                expected_year,
                fixture,
                player_identities,
                error,
            )
        except OfficialMatchDetailsUnavailable as error:
            raise ValueError(
                f"AFL match {match_id} has no official header; provide its "
                "season year and a refreshed season manifest"
            ) from error

        provenance = None
        try:
            raw_data = (
                extract_table_data(page)
                if expected_year is None
                else extract_table_data(page, expected_year=expected_year)
            )
        except OfficialPlayerStatsUnavailable as error:
            return _scrape_match_player_stats_fallback(
                browser,
                match_id,
                expected_year,
                fixture,
                player_identities,
                error,
            )
        except OfficialMatchDetailsUnavailable as error:
            if expected_year is None:
                raise ValueError(
                    f"AFL match {match_id} has no official header; provide its "
                    "season year and a refreshed season manifest"
                ) from error
            from .match_metadata import get_match_metadata_catalog
            from .metadata_fallback import resolve_fallback_match_details

            catalog = get_match_metadata_catalog(browser, expected_year)
            fallback_details, provenance = resolve_fallback_match_details(
                fixture, catalog
            )
            raw_data = extract_table_data(
                page,
                expected_year=expected_year,
                fallback_details=fallback_details,
            )
        if provenance is None:
            if fixture is not None and expected_year is not None:
                from .match_metadata import get_match_metadata_catalog
                from .metadata_fallback import (
                    cross_check_official_match_details,
                    resolve_fallback_match_details,
                )

                catalog = get_match_metadata_catalog(browser, expected_year)
                external_details, external_provenance = resolve_fallback_match_details(
                    fixture, catalog
                )
                cross_check_official_match_details(raw_data.details, external_details)
                provenance = MatchDataProvenance(
                    player_stats_url=url,
                    match_details_source="afl_official",
                    match_details_url=url,
                    official_fixture_url=fixture.source_url,
                    cross_checked_fields=external_provenance.cross_checked_fields,
                )
            else:
                provenance = MatchDataProvenance(
                    player_stats_url=url,
                    match_details_source="afl_official",
                    match_details_url=url,
                    official_fixture_url=fixture.source_url if fixture else None,
                )
        save_raw_match_data(raw_data, match_id, provenance=provenance)
        return raw_data
    except Exception as exc:
        raise RuntimeError(
            f"Failed to scrape AFL match {match_id} ({url}): {exc}"
        ) from exc
    finally:
        page.close()


def scrape_players(
    browser: BrowserContext, year: int, source: str = "afl_tables"
) -> List[Path]:
    source_obj = PlayerSourceFactory.get(source)
    page = browser.new_page()
    list_url = source_obj.get_list_page_url(year)
    staging_dir: Path | None = None
    try:
        try:
            response = page.goto(list_url)
            if source == "afl_tables":
                source_obj.validate_list_navigation(page, response, year)
            links = source_obj.scrape_players_links(page, year)
            player_ids = list(
                dict.fromkeys(
                    source_obj.player_id_from_url(urljoin(list_url, link))
                    for link in links
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to scrape {source} player list for {year} "
                f"({list_url}): {exc}"
            ) from exc

        if source == "afl_tables":
            raw_root = source_obj.get_raw_data_dir()
            raw_root.mkdir(parents=True, exist_ok=True)
            staging_dir = Path(tempfile.mkdtemp(prefix=".player-run-", dir=raw_root))

        players_data_paths = []

        for player_id in player_ids:
            player_url = source_obj.get_player_page_url(player_id)
            try:
                response = page.goto(player_url)
                if source == "afl_tables":
                    source_obj.validate_player_navigation(page, response, player_url)
                    player_data_path = source_obj.scrape_player(
                        page, player_id, output_dir=staging_dir
                    )
                else:
                    player_data_path = source_obj.scrape_player(page, player_id)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to scrape {source} player {player_id!r} "
                    f"({player_url}): {exc}"
                ) from exc
            if player_data_path is not None:
                players_data_paths.append(player_data_path)

        if source == "afl_tables":
            if len(players_data_paths) != len(player_ids):
                raise RuntimeError(
                    f"AFL Tables saved {len(players_data_paths)} of "
                    f"{len(player_ids)} player pages"
                )
            final_dir = source_obj.get_raw_data_dir() / "player"
            backup_dir = final_dir.with_name(f".player-backup-{uuid4().hex}")
            try:
                if final_dir.exists():
                    final_dir.replace(backup_dir)
                staging_dir.replace(final_dir)
                staging_dir = None
            except Exception:
                if not final_dir.exists() and backup_dir.exists():
                    backup_dir.replace(final_dir)
                raise
            else:
                if backup_dir.exists():
                    _remove_directory_best_effort(backup_dir)
            players_data_paths = [final_dir / path.name for path in players_data_paths]

        return players_data_paths
    finally:
        if staging_dir is not None and staging_dir.exists():
            _remove_directory_best_effort(staging_dir)
        page.close()
