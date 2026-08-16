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
from .storage import connection_check, test_all_connections
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
    try:
        version = connection_check()
        click.echo(test_all_connections())
        click.echo(f"✅   DB version {version}")
    except Exception as e:
        click.echo(f"❌   Failed {e}")


@cli.group(name="scrape")
def scrape():
    """
    Execute the web scraper routine.
    """
    click.echo("🕷️   Scraping...")


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


@scrape.command("season", help="Discover and save every round and match in a season")
@click.argument("year", nargs=1, type=int)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless).",
)
def season(year, headless):
    """Write a validated, year-scoped official fixture manifest."""
    with sync_browser_context(headless) as browser:
        manifest = discover_official_season(browser, year)
    path = save_season_manifest(manifest)
    click.echo(
        f"Saved {manifest.match_count} matches across {len(manifest.rounds)} "
        f"rounds to {path}"
    )


@scrape.command(
    "historical-season",
    help="Discover and optionally cache AustralianFootball matches from 2006-2011",
)
@click.argument("year", nargs=1, type=int)
@click.option(
    "--matches/--manifest-only",
    default=False,
    help="Cache every validated match page after discovering the manifest.",
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
    help="Delay between live match requests.",
)
@click.option(
    "--headless/--no-headless",
    default=False,
    help="Use headless mode; the historical source may reject fresh sessions.",
)
def historical_season(year, matches, refresh, delay_ms, headless):
    """Write a validated AustralianFootball manifest and resumable match cache."""
    from .scraper import (
        cache_australian_football_season_matches,
        discover_australian_football_season,
        save_australian_football_manifest,
    )

    with sync_browser_context(headless) as browser:
        manifest = discover_australian_football_season(browser, year)
        path = save_australian_football_manifest(manifest)
        click.echo(
            f"Saved historical season manifest covering {manifest.match_count} "
            f"matches across {len(manifest.rounds)} groups to {path}"
        )
        if not matches:
            return

        def report_progress(index, total, match_id, cached):
            if index == 1 or index == total or index % 10 == 0:
                source = "cache" if cached else "live"
                click.echo(f"[{index}/{total}] match {match_id} ({source})")

        paths = cache_australian_football_season_matches(
            browser,
            manifest,
            refresh=refresh,
            delay_ms=delay_ms,
            progress=report_progress,
        )
    click.echo(f"Validated {len(paths)} historical match caches for {year}")


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
def match(id, headless):
    print(f"Scraping match ID {id}...")
    match_pipeline(id, headless)


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
    "players", help="Transform all unstructured player data into structured format"
)
@click.option(
    "--scrape/--no-scrape",
    default=False,
    help="Run the scraper to refresh extracted data before transform and load.",
)
@click.option(
    "--year",
    default=datetime.now().year,
    type=int,
    help="The year, defaults to current if not included.",
)
def pipeline_players(scrape: bool, year=2026):
    print(players_pipeline(scrape, year))


@pipeline.command(
    "historical-season",
    help="Preflight and optionally load one cached 2006-2011 season",
)
@click.argument("year", nargs=1, type=int)
@click.option(
    "--load/--dry-run",
    default=False,
    help="Write only after complete cache, identity and reference preflight.",
)
def pipeline_historical_season(year, load):
    """Load AustralianFootball caches; safe default is validation only."""
    from .pipelines import historical_season_pipeline

    report = historical_season_pipeline(year, load=load)
    action = "Loaded" if load else "Validated"
    click.echo(
        f"{action} {report.matches} historical matches and "
        f"{report.player_stats} player-stat rows for {year}"
    )
    if load:
        click.echo(
            f"Games inserted: {report.inserted_games}; "
            f"updated: {report.updated_games}"
        )


@pipeline.command(
    "historical-backfill",
    help="Preflight, reconcile, and optionally load a cached historical range",
)
@click.option("--from-year", "start_year", default=2006, type=int, show_default=True)
@click.option("--to-year", "end_year", default=2011, type=int, show_default=True)
@click.option(
    "--load/--dry-run",
    default=False,
    help="Load only after every requested year passes preflight.",
)
@click.option(
    "--resume/--reprocess",
    default=True,
    help="Skip only years that reconcile completely with the database.",
)
@click.option(
    "--checkpoint",
    type=click.Path(path_type=Path),
    help="Override the atomic checkpoint JSON path.",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    help="Override the reconciliation report JSON path.",
)
def pipeline_historical_backfill(
    start_year, end_year, load, resume, checkpoint, report
):
    """Run the resumable 2006-2011 backfill orchestrator."""
    from .pipelines import historical_backfill_pipeline

    def progress(year, status):
        click.echo(f"[{year}] {status}")

    result = historical_backfill_pipeline(
        start_year,
        end_year,
        load=load,
        resume=resume,
        checkpoint_path=checkpoint,
        report_path=report,
        progress=progress,
    )
    for year_report in result.report.years:
        click.echo(
            f"{year_report.year}: DB matches "
            f"{year_report.database_matches}/{year_report.expected_matches}; "
            f"player stats {year_report.database_player_stats}/"
            f"{year_report.expected_player_stats}; "
            f"differences {year_report.mismatch_count}"
        )
    click.echo(
        f"Range totals: DB matches {result.report.database_matches}/"
        f"{result.report.expected_matches}; player stats "
        f"{result.report.database_player_stats}/"
        f"{result.report.expected_player_stats}; differences "
        f"{result.report.mismatch_count}"
    )
    click.echo(f"Checkpoint: {result.checkpoint_path}")
    click.echo(f"Reconciliation report: {result.report_path}")


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


@map.command("scrape")
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
def map_scrape(headless, year):
    """Scrape player IDs from both AFL official and AFL Tables sources."""
    from .scraper.scrape_player_ids import (
        scrape_player_ids,
        save_player_id_snapshots,
    )

    with sync_browser_context(headless) as browser:
        click.echo(f"Scraping AFL official players for {year}...")
        afl_players = scrape_player_ids(browser, year, "afl_official")

        click.echo(f"Scraping AFL Tables players for {year}...")
        tables_players = scrape_player_ids(browser, year, "afl_tables")
        paths = save_player_id_snapshots(
            {"afl_official": afl_players, "afl_tables": tables_players}, year
        )
        click.echo(
            f"Saved {len(afl_players)} AFL official players to "
            f"{paths['afl_official']}"
        )
        click.echo(
            f"Saved {len(tables_players)} AFL Tables players to "
            f"{paths['afl_tables']}"
        )


@map.command(
    "scrape-season",
    help="Derive historical official player IDs from completed season matches",
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
    help="A completed official fixture season (defaults to last year).",
)
@click.option(
    "--refresh/--reuse-cache",
    default=False,
    help="Re-scrape every match instead of reusing validated match JSON.",
)
def map_scrape_season(headless, year, refresh):
    """Create mapping snapshots from all participants in a completed season."""
    from .scraper import load_season_manifest, scrape_season_player_ids
    from .scraper.scrape_player_ids import (
        save_player_id_snapshots,
        scrape_player_ids,
    )

    if year >= datetime.now().year:
        raise click.UsageError(
            "scrape-season requires a completed historical season; "
            "use `map scrape` for the current roster"
        )

    manifest = load_season_manifest(year)

    def report_progress(index, total, match_id, cached):
        if index == 1 or index == total or index % 10 == 0:
            source = "cache" if cached else "live"
            click.echo(f"[{index}/{total}] match {match_id} ({source})")

    with sync_browser_context(headless) as browser:
        click.echo(
            f"Collecting AFL official participants from "
            f"{manifest.match_count} matches in {year}..."
        )
        afl_players = scrape_season_player_ids(
            browser,
            manifest,
            refresh=refresh,
            progress=report_progress,
        )

        click.echo(f"Scraping AFL Tables players for {year}...")
        tables_players = scrape_player_ids(browser, year, "afl_tables")

    paths = save_player_id_snapshots(
        {"afl_official": afl_players, "afl_tables": tables_players}, year
    )
    click.echo(
        f"Saved {len(afl_players)} participating AFL official players to "
        f"{paths['afl_official']}"
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
    """Match player IDs between AFL official and AFL Tables sources."""
    from .transform.map_players import (
        load_player_ids_from_json,
        match_players,
        save_matches_to_json,
    )

    click.echo(f"Loading player data for {year}...")
    afl_players = load_player_ids_from_json("afl_official", year)
    tables_players = load_player_ids_from_json("afl_tables", year)
    click.echo(
        f"Loaded {len(afl_players)} AFL official, {len(tables_players)} AFL Tables"
    )

    click.echo("Matching players...")
    matches = match_players(afl_players, tables_players)

    click.echo(
        f"Exact: {len(matches.exact)}, Fuzzy: {len(matches.fuzzy)}, "
        f"Unmatched AFL: {len(matches.unmatched_afl)}, Unmatched Tables: {len(matches.unmatched_tables)}"
    )

    save_matches_to_json(matches, year)
    click.echo(f"Saved matches to data/mapping/{year}_to_review.json")


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
    """Review and approve player ID mappings."""
    import json

    from .models.player import MatchResult, PlayerMapping
    from .transform.map_players import validate_mappings

    if input is None:
        input = f"data/mapping/{year}_to_review.json"

    with open(input) as f:
        data = json.load(f)
    matches = MatchResult.model_validate(data)

    approved: list[PlayerMapping] = []

    click.echo(f"\n=== Exact matches ({len(matches.exact)}) - auto-approved ===")
    for m in matches.exact:
        approved.append(PlayerMapping(afl_official_id=m.afl.id, player_id=m.tables.id))

    click.echo(f"\n=== Fuzzy matches ({len(matches.fuzzy)}) - need review ===")
    for i, m in enumerate(matches.fuzzy):
        click.echo(f"\n{i + 1}. {m.afl.display_name()} ({m.afl.team})")
        for j, opt in enumerate(m.tables):
            click.echo(f"   [{j + 1}] {opt.id} ({opt.team})")
        choice = click.prompt(
            "Select option (number, or s to skip)", default="s", show_default=False
        )
        if choice and choice.isdigit() and 1 <= int(choice) <= len(m.tables):
            selected = m.tables[int(choice) - 1]
            if any(mapping.player_id == selected.id for mapping in approved):
                click.echo(
                    f"  Skipped: AFL Tables ID {selected.id} is already approved."
                )
            else:
                approved.append(
                    PlayerMapping(
                        afl_official_id=m.afl.id,
                        player_id=selected.id,
                    )
                )

    click.echo(f"\n=== Unmatched AFL ({len(matches.unmatched_afl)}) ===")
    for p in matches.unmatched_afl:
        click.echo(f"  {p.display_name()} ({p.team}) - ID: {p.id}")
        click.echo("  Not added: an AFL Tables player is required before mapping.")

    click.echo(f"\n=== Unmatched Tables ({len(matches.unmatched_tables)}) ===")
    for p in matches.unmatched_tables:
        click.echo(
            f"  {p.display_name()} ({p.team}) - ID: {p.id}; "
            "no source identity row required"
        )

    validate_mappings(approved)

    output = f"data/mapping/{year}_approved.json"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump([mapping.model_dump() for mapping in approved], f, indent=2)
    click.echo(f"\n✅ Saved approved mappings to {output}")


@map.command("upsert")
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
    help="Input JSON file (default: data/mapping/{year}_approved.json)",
)
@click.option(
    "--require-complete/--allow-incomplete",
    default=False,
    help="Require mappings for every official ID in the year snapshot.",
)
def map_upsert(year, input, require_complete):
    """Upsert approved player ID mappings to database."""
    import json

    from .models.player import PlayerMapping

    if input is None:
        input = f"data/mapping/{year}_approved.json"

    with open(input) as f:
        data = json.load(f)
    mappings = [PlayerMapping(**m) for m in data]

    from .transform.map_players import (
        load_player_ids_from_json,
        upsert_mappings,
        validate_mapping_coverage,
    )

    if require_complete:
        required_players = load_player_ids_from_json("afl_official", year)
        validate_mapping_coverage(required_players, mappings)

    click.echo(f"Upserting {len(mappings)} mappings to database...")
    count = upsert_mappings(mappings, year)
    click.echo(f"✅ Upserted {count} mappings")


@map.command(
    "match-historical",
    help="Generate reviewed mapping candidates from historical match caches",
)
@click.option("--year", required=True, type=int)
def map_match_historical(year):
    """Match AustralianFootball participants to an AFL Tables snapshot."""
    from .pipelines.historical import historical_source_players
    from .transform import load_player_ids_from_json, match_players

    source_players = historical_source_players(year)
    canonical_players = load_player_ids_from_json("afl_tables", year)
    matches = match_players(source_players, canonical_players)
    output = Path(f"data/mapping/{year}_australian_football_to_review.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(matches.model_dump_json(by_alias=True, indent=2) + "\n")
    click.echo(
        f"Exact: {len(matches.exact)}, review: {len(matches.fuzzy)}, "
        f"unmatched source: {len(matches.unmatched_afl)}, "
        f"unmatched canonical: {len(matches.unmatched_tables)}"
    )
    click.echo(f"Saved historical mapping candidates to {output}")


@map.command(
    "review-historical",
    help="Review AustralianFootball-to-canonical player mappings",
)
@click.option("--year", required=True, type=int)
@click.option("-i", "--input", type=click.Path(exists=True, path_type=Path))
def map_review_historical(year, input):
    """Approve exact mappings and explicitly resolve ambiguous candidates."""
    import json

    from .models import MatchResult, SourcePlayerMapping
    from .transform import validate_source_mappings

    input = input or Path(f"data/mapping/{year}_australian_football_to_review.json")
    matches = MatchResult.model_validate_json(input.read_text(encoding="utf-8"))
    approved = [
        SourcePlayerMapping(source_player_id=match.afl.id, player_id=match.tables.id)
        for match in matches.exact
    ]
    click.echo(f"Auto-approved {len(approved)} exact name-and-team mappings")
    for match in matches.fuzzy:
        click.echo(f"\n{match.afl.display_name()} ({match.afl.team})")
        for index, option in enumerate(match.tables, start=1):
            click.echo(f"  [{index}] {option.id} ({option.team})")
        choice = click.prompt(
            "Select option (number, or s to skip)", default="s", show_default=False
        )
        if choice.isdigit() and 1 <= int(choice) <= len(match.tables):
            option = match.tables[int(choice) - 1]
            approved.append(
                SourcePlayerMapping(source_player_id=match.afl.id, player_id=option.id)
            )
    validate_source_mappings(approved)
    output = Path(f"data/mapping/{year}_australian_football_approved.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([mapping.model_dump() for mapping in approved], indent=2) + "\n"
    )
    click.echo(f"Saved {len(approved)} approved historical mappings to {output}")


@map.command(
    "upsert-historical",
    help="Upsert complete AustralianFootball-to-canonical player mappings",
)
@click.option("--year", required=True, type=int)
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    help="Reviewed JSON (defaults to the year-specific approved file).",
)
def map_upsert_historical(year, input):
    """Require exact cache coverage before persisting historical mappings."""
    import json

    from .models import SourcePlayerMapping
    from .pipelines.historical import historical_source_player_ids
    from .transform import upsert_source_mappings, validate_source_mapping_coverage

    input = input or Path(f"data/mapping/{year}_australian_football_approved.json")
    mappings = [
        SourcePlayerMapping.model_validate(item)
        for item in json.loads(input.read_text(encoding="utf-8"))
    ]
    validate_source_mapping_coverage(historical_source_player_ids(year), mappings)
    count = upsert_source_mappings(mappings, year, "australian_football")
    click.echo(f"✅ Upserted {count} complete historical mappings for {year}")
