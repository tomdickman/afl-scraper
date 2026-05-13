import click
from datetime import datetime

from .pipelines import match_pipeline, players_pipeline
from .scraper import (
    scrape_match_ids,
    scrape_match,
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
    default=datetime.now().year,
    type=int,
    help="The year, defaults to current if not included.",
)
def round(id, headless, year):
    print(f"Scraping round '{id}' of {year}...")
    with sync_browser_context(headless) as browser:
        ids = scrape_match_ids(browser, id, year)
        click.echo(ids)
        for id in ids:
            click.echo(scrape_match(browser, id))


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
        scrape_players(browser, year)


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
        scrape_afl_official_player_ids,
        scrape_afl_tables_player_ids,
        save_player_ids_to_json,
    )

    with sync_browser_context(headless) as browser:
        click.echo(f"Scraping AFL official players for {year}...")
        afl_players = scrape_afl_official_player_ids(browser, year)
        save_player_ids_to_json(afl_players, "afl_official", year)
        click.echo(f"Saved {len(afl_players)} AFL official players")

        click.echo(f"Scraping AFL Tables players for {year}...")
        tables_players = scrape_afl_tables_player_ids(browser, year)
        save_player_ids_to_json(tables_players, "afl_tables", year)
        click.echo(f"Saved {len(tables_players)} AFL Tables players")


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
        f"Exact: {len(matches['exact'])}, Fuzzy: {len(matches['fuzzy'])}, "
        f"Unmatched AFL: {len(matches['unmatched_afl'])}, Unmatched Tables: {len(matches['unmatched_tables'])}"
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

    if input is None:
        input = f"data/mapping/{year}_to_review.json"

    with open(input) as f:
        matches = json.load(f)

    approved = []

    click.echo(f"\n=== Exact matches ({len(matches['exact'])}) - auto-approved ===")
    for m in matches["exact"]:
        approved.append(
            {
                "afl_official_id": m["afl"]["id"],
                "player_id": m["tables"]["id"],
            }
        )

    click.echo(f"\n=== Fuzzy matches ({len(matches['fuzzy'])}) - need review ===")
    for i, m in enumerate(matches["fuzzy"]):
        afl = m["afl"]
        options = m["tables"]
        click.echo(f"\n{i + 1}. {afl['firstName']} {afl['lastName']} ({afl['team']})")
        for j, opt in enumerate(options):
            click.echo(f"   [{j + 1}] {opt['id']} ({opt['team']})")
        choice = click.prompt("Select option (number)", default="1", show_default=False)
        if choice and choice.isdigit() and 1 <= int(choice) <= len(options):
            selected = options[int(choice) - 1]
            approved.append(
                {
                    "afl_official_id": afl["id"],
                    "player_id": selected["id"],
                }
            )

    click.echo(f"\n=== Unmatched AFL ({len(matches['unmatched_afl'])}) ===")
    for m in matches["unmatched_afl"]:
        click.echo(f"  {m['firstName']} {m['lastName']} ({m['team']}) - ID: {m['id']}")
        add = click.prompt(
            "Add with null AFL ID? (y/N)", default="n", show_default=False
        )
        if add.lower() == "y":
            approved.append(
                {
                    "afl_official_id": None,
                    "player_id": m["id"],
                }
            )

    click.echo(f"\n=== Unmatched Tables ({len(matches['unmatched_tables'])}) ===")
    for m in matches["unmatched_tables"]:
        click.echo(f"  {m['firstName']} {m['lastName']} ({m['team']}) - ID: {m['id']}")
        add = click.prompt(
            "Add with null AFL ID? (y/N)", default="n", show_default=False
        )
        if add.lower() == "y":
            approved.append(
                {
                    "afl_official_id": None,
                    "player_id": m["id"],
                }
            )

    output = f"data/mapping/{year}_approved.json"
    with open(output, "w") as f:
        json.dump(approved, f, indent=2)
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
def map_upsert(year, input):
    """Upsert approved player ID mappings to database."""
    import json

    if input is None:
        input = f"data/mapping/{year}_approved.json"

    with open(input) as f:
        mappings = json.load(f)

    from .transform.map_players import upsert_mappings

    click.echo(f"Upserting {len(mappings)} mappings to database...")
    count = upsert_mappings(mappings, year)
    click.echo(f"✅ Upserted {count} mappings")
