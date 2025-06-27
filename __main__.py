import click
from scraper import scrape_matches
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

@cli.command(name="scrape")
@click.option(
    '--headless/--no-headless',
    default=True,
    help='Run the scraper in headless mode (default: headless).'
)
@click.option(
    '--round-id',
    type=str,
    default="1",
    help='Round ID to scrape (uses "0" for Opening Round).'
)
def scrape(round_id, headless):
    """
    Execute the web scraper routine.
    """
    click.echo("🕷️   Scraping...")
    click.echo(scrape_matches(round_id, headless=headless))

@cli.command(name="smoke")
def smoke():
    """
    Execute a smoke test to check for potential site changes affecting scraping.
    """
    smoke_test()

if __name__ == "__main__":
    cli()
