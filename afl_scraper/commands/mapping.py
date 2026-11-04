"""Player identity mapping CLI commands and review workflow."""

from datetime import UTC, datetime
from pathlib import Path

import click

from ..paths import data_path
from ..scraper import sync_browser_context
from ..scraper.constants import MAX_CONFIGURED_YEAR, MIN_HISTORY_YEAR


@click.group("map")
def mapping():
    """
    Execute player ID mapping workflow.
    """
    click.echo("🗺️   Player ID Mapping...")


def _generate_official_mapping_candidates(year):
    from ..transform.map_players import (
        load_player_ids_from_json,
        match_players,
        save_matches_to_json,
    )

    official_players = load_player_ids_from_json("afl_official", year)
    canonical_players = load_player_ids_from_json("afl_tables", year)
    click.echo(
        f"Loaded {len(official_players)} AFL official, "
        f"{len(canonical_players)} AFL Tables"
    )
    matches = match_players(official_players, canonical_players)
    save_matches_to_json(matches, year)
    return matches


def _generate_historical_mapping_candidates(year):
    from ..pipelines.historical import historical_source_players
    from ..transform import load_player_ids_from_json, match_players

    source_players = historical_source_players(year)
    canonical_players = load_player_ids_from_json("afl_tables", year)
    matches = match_players(source_players, canonical_players)
    output = data_path("mapping", f"{year}_australian_football_to_review.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(matches.model_dump_json(by_alias=True, indent=2) + "\n")
    return matches


def _load_official_approved_mappings(year):
    import json

    from ..models import PlayerMapping
    from ..transform.map_players import validate_mappings

    path = data_path("mapping", f"{year}_approved.json")
    if not path.exists():
        return []
    mappings = [
        PlayerMapping.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    validate_mappings(mappings)
    return mappings


def _select_review_option(options, prompt, accept_single_candidate):
    if accept_single_candidate and len(options) == 1:
        selected = options[0]
        click.echo(f"  Auto-accepted sole candidate: {selected.id}")
        return selected
    choice = click.prompt(prompt, default="s", show_default=False)
    if choice and choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice) - 1]
    return None


def _review_official_matches(
    matches,
    year,
    retained_mappings=None,
    accept_single_candidate=False,
):
    import json

    from ..models.player import PlayerMapping
    from ..transform.map_players import teams_match, validate_mappings

    approved: list[PlayerMapping] = []
    retained_mappings = list(retained_mappings or [])
    validate_mappings(retained_mappings)
    source_ids = (
        {match.afl.id for match in matches.exact}
        | {match.afl.id for match in matches.fuzzy}
        | {player.id for player in matches.unmatched_afl}
    )
    canonical_ids = (
        {match.tables.id for match in matches.exact}
        | {option.id for match in matches.fuzzy for option in match.tables}
        | {player.id for player in matches.unmatched_tables}
    )
    for mapping in retained_mappings:
        if mapping.afl_official_id not in source_ids:
            raise ValueError(
                f"Previously approved AFL Official ID "
                f"{mapping.afl_official_id!r} is not in the current snapshot; "
                "rerun with --force to discard retained decisions"
            )
        if mapping.player_id not in canonical_ids:
            raise ValueError(
                f"Previously approved AFL Tables ID {mapping.player_id!r} is not "
                "in the current snapshot; rerun with --force to discard retained "
                "decisions"
            )
    retained_by_source = {
        mapping.afl_official_id: mapping for mapping in retained_mappings
    }

    click.echo(f"\n=== Exact matches ({len(matches.exact)}) - auto-approved ===")
    for match in matches.exact:
        retained = retained_by_source.get(match.afl.id)
        if retained is not None and retained.player_id != match.tables.id:
            raise ValueError(
                f"Previously approved mapping for AFL Official ID {match.afl.id} "
                f"conflicts with exact match {match.tables.id}; rerun with --force "
                "to discard retained decisions"
            )
        approved.append(
            PlayerMapping(afl_official_id=match.afl.id, player_id=match.tables.id)
        )
    exact_source_ids = {mapping.afl_official_id for mapping in approved}
    approved.extend(
        mapping
        for mapping in retained_mappings
        if mapping.afl_official_id not in exact_source_ids
    )
    validate_mappings(approved)

    click.echo(f"\n=== Fuzzy matches ({len(matches.fuzzy)}) - need review ===")
    for index, match in enumerate(matches.fuzzy, start=1):
        click.echo(f"\n{index}. {match.afl.display_name()} ({match.afl.team})")
        retained = retained_by_source.get(match.afl.id)
        if retained is not None:
            click.echo(f"   Retained approved mapping: {retained.player_id}")
            continue
        for option_index, option in enumerate(match.tables, start=1):
            click.echo(f"   [{option_index}] {option.id} ({option.team})")
        selected = _select_review_option(
            match.tables,
            "Select option (number, or s to skip)",
            accept_single_candidate,
        )
        if selected is not None:
            if any(mapping.player_id == selected.id for mapping in approved):
                click.echo(
                    f"  Skipped: AFL Tables ID {selected.id} is already approved."
                )
            else:
                approved.append(
                    PlayerMapping(
                        afl_official_id=match.afl.id,
                        player_id=selected.id,
                    )
                )

    click.echo(f"\n=== Unmatched AFL ({len(matches.unmatched_afl)}) ===")
    for player in matches.unmatched_afl:
        click.echo(f"  {player.display_name()} ({player.team}) - ID: {player.id}")
        retained = retained_by_source.get(player.id)
        if retained is not None:
            click.echo(f"  Retained approved mapping: {retained.player_id}")
            continue
        used_player_ids = {mapping.player_id for mapping in approved}
        options = sorted(
            (
                candidate
                for candidate in matches.unmatched_tables
                if candidate.id not in used_player_ids
                and teams_match(player.team, candidate.team)
            ),
            key=lambda candidate: candidate.id,
        )
        for option_index, option in enumerate(options, start=1):
            click.echo(
                f"   [{option_index}] {option.display_name()} "
                f"({option.team}) - ID: {option.id}"
            )
        if not options:
            click.echo("  Not added: an AFL Tables player is required before mapping.")
            continue
        selected = _select_review_option(
            options,
            "Select unmatched option (number, or s to skip)",
            accept_single_candidate,
        )
        if selected is not None:
            approved.append(
                PlayerMapping(
                    afl_official_id=player.id,
                    player_id=selected.id,
                )
            )

    used_player_ids = {mapping.player_id for mapping in approved}
    unmatched_tables = [
        player
        for player in matches.unmatched_tables
        if player.id not in used_player_ids
    ]
    click.echo(f"\n=== Unmatched Tables ({len(unmatched_tables)}) ===")
    for player in unmatched_tables:
        click.echo(
            f"  {player.display_name()} ({player.team}) - ID: {player.id}; "
            "no source identity row required"
        )

    validate_mappings(approved)
    output = data_path("mapping", f"{year}_approved.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([mapping.model_dump() for mapping in approved], indent=2) + "\n"
    )
    click.echo(f"\n✅ Saved approved mappings to {output}")
    return approved


def _review_historical_matches(matches, year, accept_single_candidate=False):
    import json

    from ..models import SourcePlayerMapping
    from ..transform import validate_source_mappings

    approved = [
        SourcePlayerMapping(
            source_player_id=match.afl.id,
            player_id=match.tables.id,
        )
        for match in matches.exact
    ]
    click.echo(f"Auto-approved {len(approved)} exact name-and-team mappings")
    for match in matches.fuzzy:
        click.echo(f"\n{match.afl.display_name()} ({match.afl.team})")
        for index, option in enumerate(match.tables, start=1):
            click.echo(f"  [{index}] {option.id} ({option.team})")
        option = _select_review_option(
            match.tables,
            "Select option (number, or s to skip)",
            accept_single_candidate,
        )
        if option is not None:
            if any(mapping.player_id == option.id for mapping in approved):
                click.echo(f"  Skipped: AFL Tables ID {option.id} is already approved.")
            else:
                approved.append(
                    SourcePlayerMapping(
                        source_player_id=match.afl.id,
                        player_id=option.id,
                    )
                )
    validate_source_mappings(approved)
    output = data_path("mapping", f"{year}_australian_football_approved.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([mapping.model_dump() for mapping in approved], indent=2) + "\n"
    )
    click.echo(f"Saved {len(approved)} approved historical mappings to {output}")
    return approved


def _official_mapping_is_complete(year):
    import json

    from ..models import PlayerMapping
    from ..transform.map_players import (
        load_player_ids_from_json,
        validate_mapping_coverage,
    )

    path = data_path("mapping", f"{year}_approved.json")
    if not path.exists():
        return False
    try:
        mappings = [
            PlayerMapping.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]
        validate_mapping_coverage(
            load_player_ids_from_json("afl_official", year), mappings
        )
    except (OSError, ValueError):
        return False
    return True


def _historical_mapping_is_complete(year):
    import json

    from ..models import SourcePlayerMapping
    from ..pipelines.historical import historical_source_player_ids
    from ..transform import validate_source_mapping_coverage

    path = data_path("mapping", f"{year}_australian_football_approved.json")
    if not path.exists():
        return False
    try:
        mappings = [
            SourcePlayerMapping.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]
        validate_source_mapping_coverage(historical_source_player_ids(year), mappings)
    except (OSError, ValueError):
        return False
    return True


@mapping.command(
    "scrape",
    help="Derive source player identities for any configured cached season",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
@click.option(
    "--year",
    default=lambda: datetime.now(UTC).year - 1,
    type=int,
    help="A completed season (defaults to last year).",
)
@click.option(
    "--refresh/--reuse-cache",
    default=False,
    help="Re-scrape every match instead of reusing validated match JSON.",
)
def map_scrape(headless, year, refresh):
    """Create mapping snapshots from a provider-routed completed season."""
    from ..pipelines.historical import historical_source_players
    from ..pipelines.historical_players import load_player_snapshot
    from ..scraper import load_season_manifest, scrape_season_player_ids
    from ..scraper.scrape_player_ids import save_player_id_snapshots
    from ..season_routing import season_plan

    if year > datetime.now(UTC).year:
        raise click.UsageError("map scrape cannot process a future season")
    plan = season_plan(year)

    def report_progress(index, total, match_id, cached):
        if index == 1 or index == total or index % 10 == 0:
            source = "cache" if cached else "live"
            click.echo(f"[{index}/{total}] match {match_id} ({source})")

    if plan.match_source == "australian_football":
        source_players = historical_source_players(year)
    else:
        manifest = load_season_manifest(year)
        click.echo(
            f"Collecting {plan.display_source} participants from "
            f"{manifest.match_count} matches in {year}..."
        )
        with sync_browser_context(headless) as browser:
            source_players = scrape_season_player_ids(
                browser,
                manifest,
                refresh=refresh,
                progress=report_progress,
            )

    tables_players = load_player_snapshot(year)

    paths = save_player_id_snapshots(
        {plan.match_source: source_players, "afl_tables": tables_players}, year
    )
    click.echo(
        f"Saved {len(source_players)} participating {plan.display_source} "
        f"players to {paths[plan.match_source]}"
    )
    click.echo(
        f"Saved {len(tables_players)} AFL Tables players to " f"{paths['afl_tables']}"
    )


@mapping.command("match")
@click.option(
    "--year",
    default=datetime.now(UTC).year,
    type=int,
    help="The year, defaults to current if not included.",
)
def map_match(year):
    """Generate mapping candidates using the configured source for a year."""
    from ..season_routing import season_plan

    plan = season_plan(year)
    click.echo(f"[{year}] source: {plan.display_source}")
    matches = (
        _generate_historical_mapping_candidates(year)
        if plan.match_source == "australian_football"
        else _generate_official_mapping_candidates(year)
    )

    click.echo(
        f"Exact: {len(matches.exact)}, review: {len(matches.fuzzy)}, "
        f"unmatched source: {len(matches.unmatched_afl)}, "
        f"unmatched canonical: {len(matches.unmatched_tables)}"
    )
    click.echo(f"Saved mapping candidates to {plan.review_mapping_path}")


@mapping.command("review")
@click.option(
    "--year",
    default=datetime.now(UTC).year,
    type=int,
    help="The year, defaults to current if not included.",
)
@click.option(
    "-i",
    "--input",
    default=None,
    type=click.Path(exists=True),
    help="Input JSON file (default: data/mapping/{year}_to_review.json)",
)
def map_review(year, input):
    """Review mappings using the configured source for a year."""
    from ..models.player import MatchResult
    from ..season_routing import season_plan

    plan = season_plan(year)
    input = Path(input) if input is not None else plan.review_mapping_path
    matches = MatchResult.model_validate_json(input.read_text(encoding="utf-8"))

    if plan.match_source == "australian_football":
        _review_historical_matches(matches, year)
    else:
        _review_official_matches(matches, year)


@mapping.command("upsert")
@click.option(
    "--year",
    default=None,
    type=int,
    help="Upsert one year; defaults to the current year when no range is given.",
)
@click.option(
    "--from-year",
    "start_year",
    type=int,
    help="First year in an inclusive upsert range.",
)
@click.option(
    "--to-year",
    "end_year",
    type=int,
    help="Last year in an inclusive upsert range.",
)
@click.option(
    "-i",
    "--input",
    default=None,
    type=click.Path(exists=True),
    help="Input JSON file (default: data/mapping/{year}_approved.json)",
)
@click.option(
    "--require-complete/--allow-incomplete",
    default=False,
    help="Require mappings for every official ID in the year snapshot.",
)
def map_upsert(year, start_year, end_year, input, require_complete):
    """Upsert approved player ID mappings for one year or an inclusive range."""
    import json

    from ..models import PlayerMapping, SourcePlayerMapping
    from ..pipelines.historical import historical_source_player_ids
    from ..season_routing import season_plan, season_years
    from ..transform import (
        upsert_source_mapping_years,
        validate_source_mapping_coverage,
    )
    from ..transform.map_players import load_player_ids_from_json

    range_requested = start_year is not None or end_year is not None
    if year is not None and range_requested:
        raise click.UsageError("--year cannot be combined with --from-year/--to-year")
    if (start_year is None) != (end_year is None):
        raise click.UsageError("--from-year and --to-year must be provided together")
    if input is not None and range_requested:
        raise click.UsageError("--input can only be used with a single --year")

    if range_requested:
        try:
            years = season_years(start_year, end_year)
        except ValueError as error:
            raise click.UsageError(str(error)) from error
    else:
        years = [year if year is not None else datetime.now(UTC).year]

    mappings_by_source_year = {}
    display_counts = {}
    for mapping_year in years:
        plan = season_plan(mapping_year)
        mapping_input = Path(input) if input else plan.approved_mapping_path
        data = json.loads(mapping_input.read_text(encoding="utf-8"))
        if plan.match_source == "australian_football":
            mappings = [SourcePlayerMapping.model_validate(item) for item in data]
            required_ids = (
                historical_source_player_ids(mapping_year)
                if require_complete
                else set()
            )
        else:
            official_mappings = [PlayerMapping.model_validate(item) for item in data]
            mappings = [
                SourcePlayerMapping(
                    source_player_id=item.afl_official_id,
                    player_id=item.player_id,
                )
                for item in official_mappings
                if item.afl_official_id is not None
            ]
            required_ids = (
                {
                    item.id
                    for item in load_player_ids_from_json("afl_official", mapping_year)
                }
                if require_complete
                else set()
            )
        if require_complete:
            validate_source_mapping_coverage(required_ids, mappings)
        mappings_by_source_year[(plan.match_source, mapping_year)] = mappings
        display_counts[mapping_year] = len(mappings)

    if len(mappings_by_source_year) == 1:
        (source, mapping_year), mappings = next(iter(mappings_by_source_year.items()))
        click.echo(f"Upserting {len(mappings)} {source} mappings to database...")
        count = upsert_source_mapping_years(mappings_by_source_year)[
            (source, mapping_year)
        ]
        click.echo(f"✅ Upserted {count} mappings")
        return

    click.echo(
        f"Upserting {sum(display_counts.values())} mappings "
        f"across {len(display_counts)} years..."
    )
    counts = upsert_source_mapping_years(mappings_by_source_year)
    for (_source, mapping_year), count in counts.items():
        click.echo(f"[{mapping_year}] ✅ Upserted {count} mappings")
    click.echo(
        f"✅ Upserted {sum(counts.values())} mappings across {len(counts)} years"
    )


@mapping.command(
    "review-all",
    help="Review every incomplete player mapping year in one resumable run",
)
@click.option(
    "--from-year",
    "start_year",
    default=MIN_HISTORY_YEAR,
    type=click.IntRange(MIN_HISTORY_YEAR, MAX_CONFIGURED_YEAR),
    show_default=True,
)
@click.option(
    "--to-year",
    "end_year",
    default=MAX_CONFIGURED_YEAR,
    type=click.IntRange(MIN_HISTORY_YEAR, MAX_CONFIGURED_YEAR),
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-review years whose approved mapping files are already complete.",
)
@click.option(
    "--accept-single-candidate",
    is_flag=True,
    help="Automatically approve review items that have exactly one candidate.",
)
def map_review_all(start_year, end_year, force, accept_single_candidate):
    """Regenerate candidates and review incomplete mappings across all years."""
    from ..pipelines.historical import historical_source_player_ids
    from ..season_routing import season_plan
    from ..transform import validate_source_mapping_coverage
    from ..transform.map_players import (
        load_player_ids_from_json,
        validate_mapping_coverage,
    )

    if start_year > end_year:
        raise click.UsageError("--from-year must be less than or equal to --to-year")

    completed = []
    skipped = []
    incomplete = []
    for year in range(start_year, end_year + 1):
        plan = season_plan(year)
        historical = plan.match_source == "australian_football"
        is_complete = (
            _historical_mapping_is_complete(year)
            if historical
            else _official_mapping_is_complete(year)
        )
        if is_complete and not force:
            skipped.append(year)
            click.echo(f"[{year}] complete; skipping")
            continue

        click.echo(f"\n[{year}] reviewing {plan.display_source} player mappings")
        try:
            if historical:
                matches = _generate_historical_mapping_candidates(year)
                mappings = _review_historical_matches(
                    matches,
                    year,
                    accept_single_candidate=accept_single_candidate,
                )
                validate_source_mapping_coverage(
                    historical_source_player_ids(year), mappings
                )
            else:
                matches = _generate_official_mapping_candidates(year)
                retained = [] if force else _load_official_approved_mappings(year)
                mappings = _review_official_matches(
                    matches,
                    year,
                    retained_mappings=retained,
                    accept_single_candidate=accept_single_candidate,
                )
                validate_mapping_coverage(
                    load_player_ids_from_json("afl_official", year), mappings
                )
        except (click.Abort, KeyboardInterrupt):
            raise
        except Exception as error:
            incomplete.append((year, str(error)))
            click.echo(f"[{year}] incomplete: {error}", err=True)
            continue

        completed.append(year)
        click.echo(f"[{year}] mapping coverage complete")

    click.echo(
        f"\nReview summary: {len(completed)} completed, "
        f"{len(skipped)} already complete, {len(incomplete)} incomplete."
    )
    if incomplete:
        years = ", ".join(str(year) for year, _ in incomplete)
        raise click.ClickException(
            f"mapping review remains incomplete for: {years}; "
            "resolve the reported candidates or source data, then rerun review-all"
        )
