import click
from datetime import datetime
from pathlib import Path

from .pipelines import match_pipeline, players_pipeline
from .scraper import (
    discover_official_season,
    save_season_manifest,
    scrape_players,
    sync_browser_context,
)
from .scraper.constants import (
    MAX_CONFIGURED_YEAR,
    MIN_HISTORY_YEAR,
    OFFICIAL_FIXTURE_MIN_YEAR,
)
from .storage import test_all_connections
from .utils import health_check, smoke_test


@click.group()
def cli():
    """
    Handles various scraping tasks to ascertain AFL statistics.
    """
    pass


@cli.command(name="health")
def health():
    """
    Run a system health check.
    """
    if health_check():
        click.echo("✅   Pass")
    else:
        click.echo("❌   Failed")


@cli.command(name="dbcheck")
def dbcheck():
    """
    Run a database connection check.
    """
    results = test_all_connections()
    failures = []
    for result in results.values():
        connection_type = result["connection_type"]
        if result["status"] == "success":
            click.echo(f"✅   {connection_type}: {result['version']}")
            continue
        failures.append(connection_type)
        click.echo(
            f"❌   {connection_type}: {result['error']}",
            err=True,
        )
    if failures:
        raise click.ClickException(
            "database connection check failed for " + ", ".join(failures)
        )


@cli.group(name="database")
def database():
    """Manage the local development database."""


@database.command(name="reset")
@click.option(
    "--confirm-database",
    metavar="NAME",
    help="Exact DB_NAME confirmation; prompts when omitted.",
)
@click.option(
    "--migrate/--no-migrate",
    default=True,
    help="Apply checked-out migrations after clearing the schema (default: migrate).",
)
def database_reset(confirm_database, migrate):
    """Irreversibly clear and rebuild a disposable local PostgreSQL database."""
    from .storage.reset import (
        get_development_database_target,
        reset_public_schema,
        upgrade_database_to_head,
    )

    try:
        target = get_development_database_target()
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"WARNING: this permanently deletes every object in public on "
        f"{target.host}:{target.port}/{target.name}."
    )
    click.echo("Files under data/ are not deleted.")
    if confirm_database is None:
        confirm_database = click.prompt("Type the database name to continue")
    if confirm_database != target.name:
        raise click.ClickException("database confirmation did not match DB_NAME")

    try:
        reset_public_schema(target)
    except Exception as error:
        raise click.ClickException(f"database reset failed: {error}") from error
    click.echo(f"Cleared PostgreSQL schema public in {target.name}")

    if not migrate:
        click.echo("Database left empty (--no-migrate).")
        return

    try:
        upgrade_database_to_head()
    except Exception as error:
        raise click.ClickException(
            "schema was cleared, but migration to head failed: " f"{error}"
        ) from error
    click.echo("Rebuilt database schema at Alembic head")


@cli.group(name="scrape")
def scrape():
    """
    Execute the web scraper routine.
    """
    click.echo("🕷️   Scraping...")


@cli.group(name="audit")
def audit():
    """Run read-only checks over raw scraping evidence."""


@audit.command("match-metadata")
@click.option("--year", required=True, type=int, help="Official season to audit.")
@click.option(
    "--refresh/--reuse-cache",
    default=False,
    help="Refresh the AFL Tables season catalogue before auditing.",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the browser in headless mode (default: headless).",
)
def audit_match_metadata_command(year, refresh, headless):
    """Verify every official fixture has one cross-source metadata identity."""
    from .scraper import (
        audit_match_metadata,
        get_match_metadata_catalog,
        load_match_metadata_catalog,
        load_season_manifest,
        save_match_metadata_audit,
    )

    try:
        manifest = load_season_manifest(year)
        try:
            if refresh:
                raise FileNotFoundError
            catalog = load_match_metadata_catalog(year)
        except FileNotFoundError:
            with sync_browser_context(headless) as browser:
                catalog = get_match_metadata_catalog(browser, year, refresh=refresh)
        report = audit_match_metadata(manifest, catalog)
        path = save_match_metadata_audit(report)
    except Exception as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"Resolved {report['resolved_count']}/{report['match_count']} match "
        f"identities; report: {path}"
    )
    if report["unresolved_count"]:
        raise click.ClickException(
            f"{report['unresolved_count']} match metadata identities are unresolved"
        )


@scrape.command(
    "round",
    help="Scrape details of all the matches in a specific round for current season",
)
@click.argument(
    "round_number",
    nargs=1,
    type=str,
    default="1",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
@click.option(
    "--year",
    default=datetime.now().year,
    type=int,
    help="The year, defaults to current if not included.",
)
@click.option(
    "--load/--no-load",
    default=True,
    help="Load data into database after scraping.",
)
def round(round_number, headless, year, load):
    from .pipelines import round_pipeline

    results = round_pipeline(round_number, year, headless, load)
    click.echo(f"\nProcessed {len(results)} matches in round {round_number}")


@scrape.command(
    "season",
    help="Discover and optionally cache every match for any configured season",
)
@click.argument("year", nargs=1, type=int)
@click.option(
    "--matches/--manifest-only",
    default=False,
    help="Cache every validated match after discovering the manifest.",
)
@click.option(
    "--refresh/--reuse-cache",
    default=False,
    help="Re-scrape existing validated match caches.",
)
@click.option(
    "--delay-ms",
    default=500,
    type=click.IntRange(min=0),
    show_default=True,
    help="Delay between live match requests when supported by the source.",
)
@click.option(
    "--headless/--no-headless",
    default=False,
    help="Use headless mode; some configured sources may reject fresh sessions.",
)
def season(year, matches, refresh, delay_ms, headless):
    """Route season acquisition to the configured source for the requested year."""
    from .season_routing import season_plan
    from .scraper import (
        cache_australian_football_season_matches,
        discover_australian_football_season,
        save_australian_football_manifest,
        scrape_season_player_ids,
    )

    plan = season_plan(year)
    click.echo(f"[{year}] source: {plan.display_source}")
    with sync_browser_context(headless) as browser:
        if plan.match_source == "australian_football":
            manifest = discover_australian_football_season(browser, year)
            path = save_australian_football_manifest(manifest)
        else:
            manifest = discover_official_season(browser, year)
            path = save_season_manifest(manifest)

        def report_progress(index, total, match_id, cached):
            if index == 1 or index == total or index % 10 == 0:
                source = "cache" if cached else "live"
                click.echo(f"[{index}/{total}] match {match_id} ({source})")

        if matches and plan.match_source == "australian_football":
            cached_count = len(
                cache_australian_football_season_matches(
                    browser,
                    manifest,
                    refresh=refresh,
                    delay_ms=delay_ms,
                    progress=report_progress,
                )
            )
        elif matches:
            scrape_season_player_ids(
                browser,
                manifest,
                refresh=refresh,
                progress=report_progress,
            )
            cached_count = manifest.match_count
        else:
            cached_count = None

    click.echo(
        f"Saved {manifest.match_count} matches across {len(manifest.rounds)} "
        f"rounds to {path}"
    )
    if cached_count is not None:
        click.echo(
            f"Validated {cached_count} {plan.display_source} match caches for {year}"
        )


@scrape.command("match", help="Scrape details a specific match by ID")
@click.argument(
    "id",
    nargs=1,
    type=str,
    default="1",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
@click.option(
    "--year",
    type=int,
    help="Season year; required for metadata fallback on legacy broken headers.",
)
def match(id, headless, year):
    print(f"Scraping match ID {id}...")
    match_pipeline(id, headless, year=year)


@scrape.command("players", help="Scrape player details for a specific year")
@click.argument("year", nargs=1, type=int, default=2025)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
def players(year, headless):
    with sync_browser_context(headless) as browser:
        paths = scrape_players(browser, year)
    click.echo(f"Saved {len(paths)} player pages")


@scrape.command(
    "all",
    help="Cache and validate every configured raw season without PostgreSQL access",
)
@click.option(
    "--from-year",
    "start_year",
    default=MIN_HISTORY_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--to-year",
    "end_year",
    default=MAX_CONFIGURED_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Deliberately replace all manifests, matches, snapshots, and profiles.",
)
@click.option(
    "--headless/--no-headless",
    default=False,
    help="Use headless mode; AustralianFootball may reject fresh headless sessions.",
)
@click.option(
    "--delay-ms",
    default=500,
    type=click.IntRange(min=0),
    show_default=True,
    help="Delay between live requests to sources that support throttling.",
)
def scrape_all(start_year, end_year, refresh, headless, delay_ms):
    """Build the complete resumable raw-data lake and mapping audit catalog."""
    from .pipelines.raw_all import scrape_all_raw_data

    report = scrape_all_raw_data(
        start_year,
        end_year,
        refresh=refresh,
        headless=headless,
        delay_ms=delay_ms,
        progress=click.echo,
    )
    click.echo(
        f"Validated {report.sources} source-seasons across {report.years} years, "
        f"{report.matches} distinct matches, "
        f"{report.player_stats} player-stat rows, and "
        f"{report.afl_tables_players} AFL Tables player profiles"
    )
    click.echo(
        f"Player profiles downloaded: {report.downloaded_profiles}; "
        f"reused: {report.reused_profiles}"
    )
    click.echo(f"Audit report: data/raw/catalog/{start_year}-{end_year}-report.json")


@cli.group("transform")
def transform():
    """
    Execute a transform routine.
    """
    click.echo("🧩   Transforming...")


@transform.command(
    "players", help="Transform all unstructured player data into structured format"
)
def transform_players():
    players_pipeline()


@cli.group("pipeline")
def pipeline():
    """
    Execute a full ETL pipeline.
    """
    click.echo("⚙️   Running pipeline...")


@pipeline.command(
    "players", help="Prepare and optionally load players for any season range"
)
@click.option(
    "--from-year",
    "start_year",
    default=MIN_HISTORY_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--to-year",
    "end_year",
    default=MAX_CONFIGURED_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--load/--dry-run",
    default=False,
    help="Upsert canonical players only after all profiles validate.",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Deliberately replace requested snapshots and profiles.",
)
@click.option(
    "--offline",
    is_flag=True,
    help="Require complete valid local caches and make no web requests.",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run live AFL Tables requests in headless mode.",
)
@click.option(
    "--delay-ms",
    default=500,
    type=click.IntRange(min=0),
    show_default=True,
    help="Delay between live AFL Tables requests.",
)
def pipeline_players(start_year, end_year, load, refresh, offline, headless, delay_ms):
    """Prepare canonical AFL Tables players across the configured range."""
    from .pipelines import prepare_players

    report = prepare_players(
        start_year,
        end_year,
        load=load,
        refresh=refresh,
        offline=offline,
        headless=headless,
        delay_ms=delay_ms,
        progress=click.echo,
    )
    action = "Loaded" if load else "Prepared"
    click.echo(
        f"{action} {report.unique_players} unique AFL Tables players across "
        f"{report.snapshots} season snapshots ({report.start_year}-{report.end_year})"
    )
    click.echo(
        f"Profiles downloaded: {report.downloaded_profiles}; "
        f"reused: {report.reused_profiles}"
    )
    if load:
        click.echo(
            f"Players inserted: {report.inserted_players}; "
            f"updated: {report.updated_players}"
        )


@pipeline.command(
    "season",
    help="Preflight and optionally load any configured cached season",
)
@click.argument("year", nargs=1, type=int)
@click.option(
    "--load/--dry-run",
    default=False,
    help="Write only after complete cache, mapping and reference preflight.",
)
def pipeline_season(year, load):
    """Route preparation and loading through the configured season source."""
    from .pipelines import season_pipeline

    def progress(index, total, source_match_id, inserted):
        if index == 1 or index == total or index % 10 == 0:
            action = "inserted" if inserted else "updated"
            click.echo(f"[{index}/{total}] match {source_match_id} ({action})")

    try:
        result = season_pipeline(year, load=load, progress=progress)
    except Exception as error:
        raise click.ClickException(str(error)) from error

    action = "Loaded" if load else "Validated"
    click.echo(
        f"{action} {result.matches} matches and {result.player_stats} "
        f"player-stat rows for {year} from {result.source}"
    )
    if not load:
        click.echo("Database writes: 0 (dry run)")
    elif result.already_reconciled:
        click.echo("Database already reconciled; writes: 0")
    else:
        click.echo(
            f"Games inserted: {result.inserted_games}; "
            f"updated: {result.updated_games}; reconciliation differences: 0"
        )


@pipeline.command(
    "backfill",
    help="Preflight and optionally load an inclusive configured season range",
)
@click.option(
    "--from-year",
    "start_year",
    default=MIN_HISTORY_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--to-year",
    "end_year",
    default=MAX_CONFIGURED_YEAR,
    type=int,
    show_default=True,
)
@click.option(
    "--load/--dry-run",
    default=False,
    help="Load only after every requested year passes preflight.",
)
def pipeline_backfill(start_year, end_year, load):
    """Run a provider-routed multi-season backfill."""
    from .pipelines import backfill_pipeline

    def progress(year, status):
        click.echo(f"[{year}] {status}")

    try:
        result = backfill_pipeline(
            start_year,
            end_year,
            load=load,
            progress=progress,
        )
    except Exception as error:
        raise click.ClickException(str(error)) from error

    for report in result.years:
        reconciliation = report.reconciliation
        click.echo(
            f"{report.year} ({report.source}): DB matches "
            f"{reconciliation.database_matches}/{reconciliation.expected_matches}; "
            f"player stats {reconciliation.database_player_stats}/"
            f"{reconciliation.expected_player_stats}; differences "
            f"{reconciliation.mismatch_count}"
        )
    click.echo(
        f"Range totals: {result.matches} matches and "
        f"{result.player_stats} player-stat rows"
    )


@cli.command(name="smoke")
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
def smoke(headless):
    """
    Execute a smoke test to check for potential site changes affecting scraping.
    """
    smoke_test(headless)


@cli.group("map")
def map():
    """
    Execute player ID mapping workflow.
    """
    click.echo("🗺️   Player ID Mapping...")


def _generate_official_mapping_candidates(year):
    from .transform.map_players import (
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
    from .pipelines.historical import historical_source_players
    from .transform import load_player_ids_from_json, match_players

    source_players = historical_source_players(year)
    canonical_players = load_player_ids_from_json("afl_tables", year)
    matches = match_players(source_players, canonical_players)
    output = Path(f"data/mapping/{year}_australian_football_to_review.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(matches.model_dump_json(by_alias=True, indent=2) + "\n")
    return matches


def _load_official_approved_mappings(year):
    import json

    from .models import PlayerMapping
    from .transform.map_players import validate_mappings

    path = Path(f"data/mapping/{year}_approved.json")
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

    from .models.player import PlayerMapping
    from .transform.map_players import teams_match, validate_mappings

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
    output = Path(f"data/mapping/{year}_approved.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([mapping.model_dump() for mapping in approved], indent=2) + "\n"
    )
    click.echo(f"\n✅ Saved approved mappings to {output}")
    return approved


def _review_historical_matches(matches, year, accept_single_candidate=False):
    import json

    from .models import SourcePlayerMapping
    from .transform import validate_source_mappings

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
    output = Path(f"data/mapping/{year}_australian_football_approved.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([mapping.model_dump() for mapping in approved], indent=2) + "\n"
    )
    click.echo(f"Saved {len(approved)} approved historical mappings to {output}")
    return approved


def _official_mapping_is_complete(year):
    import json

    from .models import PlayerMapping
    from .transform.map_players import (
        load_player_ids_from_json,
        validate_mapping_coverage,
    )

    path = Path(f"data/mapping/{year}_approved.json")
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

    from .models import SourcePlayerMapping
    from .pipelines.historical import historical_source_player_ids
    from .transform import validate_source_mapping_coverage

    path = Path(f"data/mapping/{year}_australian_football_approved.json")
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


@map.command(
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
    default=lambda: datetime.now().year - 1,
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
    from .pipelines.historical import historical_source_players
    from .pipelines.historical_players import load_player_snapshot
    from .scraper import load_season_manifest, scrape_season_player_ids
    from .scraper.scrape_player_ids import save_player_id_snapshots
    from .season_routing import season_plan

    if year > datetime.now().year:
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


@map.command("match")
@click.option(
    "--year",
    default=datetime.now().year,
    type=int,
    help="The year, defaults to current if not included.",
)
def map_match(year):
    """Generate mapping candidates using the configured source for a year."""
    from .season_routing import season_plan

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


@map.command("review")
@click.option(
    "--year",
    default=datetime.now().year,
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
    from .models.player import MatchResult
    from .season_routing import season_plan

    plan = season_plan(year)
    input = Path(input) if input is not None else plan.review_mapping_path
    matches = MatchResult.model_validate_json(input.read_text(encoding="utf-8"))

    if plan.match_source == "australian_football":
        _review_historical_matches(matches, year)
    else:
        _review_official_matches(matches, year)


@map.command("upsert")
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

    from .models import PlayerMapping, SourcePlayerMapping
    from .pipelines.historical import historical_source_player_ids
    from .season_routing import season_plan, season_years
    from .transform import (
        upsert_source_mapping_years,
        validate_source_mapping_coverage,
    )
    from .transform.map_players import load_player_ids_from_json

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
        years = [year if year is not None else datetime.now().year]

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


@map.command(
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
    from .pipelines.historical import historical_source_player_ids
    from .season_routing import season_plan
    from .transform import validate_source_mapping_coverage
    from .transform.map_players import (
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
