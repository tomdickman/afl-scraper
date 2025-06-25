import argparse
from scraper import scrape
from utils import health_check

def _run():
    parser = argparse.ArgumentParser(
        prog='AFL Scraper',
        description='Handles various scraping tasks to ascertain AFL statistics',
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        'command',
        choices=['health', 'scrape'],
        help=(
            "Command to execute:\n"
            "  health - Run a system health check.\n"
            "  scrape - Execute the web scraper routine."
        )
    )
    
    args = parser.parse_args()
    
    match args.command:
        case 'health':
            if health_check():
                print('✅   Pass')
            else:
                print('❌   Failed')
        case 'scrape':
            print("🕷️   Scraping...")
            print(scrape())
        case _:
            print("❌   Unknown Command")
    


if __name__ == "__main__":
    _run()
