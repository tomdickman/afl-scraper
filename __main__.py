import click
from scraper import scrape_matches, scrape_match
from utils import health_check, smoke_test

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

@cli.group(name="scrape")
def scrape():
    """
    Execute the web scraper routine.
    """
    click.echo("🕷️   Scraping...")

@scrape.command(
    "round",
    help="Scrape details of all the matches in a specific round for current season"
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
    help="Run the scraper in headless mode (default: headless)."
)
def round(id, headless):
    print(f"Scraping round ID {id}...")
    click.echo(scrape_matches(id, headless=headless))

@scrape.command(
    "match",
    help="Scrape details a specific match by ID"
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
    help="Run the scraper in headless mode (default: headless)."
)
def match(id, headless):
    print(f"Scraping match ID {id}...")
    click.echo(scrape_match(id, headless=headless))

@cli.command(name="smoke")
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run the scraper in headless mode (default: headless)."
)
def smoke(headless):
    """
    Execute a smoke test to check for potential site changes affecting scraping.
    """
    smoke_test(headless)

if __name__ == "__main__":
    cli()
