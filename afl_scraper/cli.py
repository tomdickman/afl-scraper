from datetime import UTC, datetime

import click

from .commands.mapping import mapping
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
    default=datetime.now(UTC).year,
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

    def progress(status, match_id, detail):
        if status == "discovered":
            click.echo(f"Found {detail} in round {round_number}")
        elif status == "failed":
            click.echo(f"Match {match_id} failed: {detail}", err=True)

    results = round_pipeline(round_number, year, headless, load, progress=progress)
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
    from .scraper import (
        cache_australian_football_season_matches,
        discover_australian_football_season,
        save_australian_football_manifest,
        scrape_season_player_ids,
    )
    from .season_routing import season_plan

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
    "match_id",
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
def match(match_id, headless, year):
    click.echo(f"Scraping match ID {match_id}...")
    match_pipeline(match_id, headless, year=year)


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
    if smoke_test(headless):
        click.echo("✅   Fixture smoke test passed")
    else:
        raise click.ClickException("Fixture smoke test failed")


cli.add_command(mapping)
