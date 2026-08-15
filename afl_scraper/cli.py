import click
from datetime import datetime
from pathlib import Path

from .pipelines import match_pipeline, players_pipeline
from .scraper import (
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
        click.echo(f"  {p.display_name()} ({p.team}) - ID: {p.id}")
        add = click.prompt(
            "Add AFL Tables-only player without an AFL Official ID? (y/N)",
            default="n",
            show_default=False,
        )
        if add.lower() == "y":
            approved.append(PlayerMapping(player_id=p.id))

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
def map_upsert(year, input):
    """Upsert approved player ID mappings to database."""
    import json

    from .models.player import PlayerMapping

    if input is None:
        input = f"data/mapping/{year}_approved.json"

    with open(input) as f:
        data = json.load(f)
    mappings = [PlayerMapping(**m) for m in data]

    from .transform.map_players import upsert_mappings

    click.echo(f"Upserting {len(mappings)} mappings to database...")
    count = upsert_mappings(mappings, year)
    click.echo(f"✅ Upserted {count} mappings")
