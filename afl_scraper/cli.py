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
def pipeline_players(scrape: bool):
    print(players_pipeline(scrape))


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
