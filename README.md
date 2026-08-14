# AFL Scraper

A Python CLI for collecting Australian Football League data, normalising it, and loading it into PostgreSQL. It combines browser-based scraping with repeatable ETL pipelines for players, matches, player game statistics, and cross-source player IDs.

## Capabilities

- Scrape a single AFL match or every match in a round.
- Capture match metadata, scores, teams, venues, and detailed player game statistics.
- Scrape player records into a local raw-data lake for later processing.
- Transform player and match data into validated models and upsert it into PostgreSQL.
- Match player IDs across configured sources, including an interactive review workflow for ambiguous and unmatched players.
- Run browser, fixture-selector, and database connection checks to detect local setup or upstream source changes.
- Manage the SQL-first PostgreSQL schema with Alembic migrations. The schema includes teams, venues, players, games, player game statistics, and player ID mappings.

The fixture scraper currently includes season IDs for 2025 and 2026. Add new seasons to `afl_scraper/scraper/constants/season_ids.py` before using `scrape round` with another year.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/) for installing and running the project
- Chromium, installed through Playwright
- PostgreSQL for commands that transform or load data

Network access is required for scraping and web health checks.

## Install

Clone the repository and install the locked dependencies:

```sh
git clone git@github.com:tomdickman/afl-scraper.git
cd afl-scraper
uv sync
uv run playwright install chromium
```

Run the CLI through `uv`:

```sh
uv run afl-scraper --help
```

Alternatively, activate the environment created by `uv sync` and invoke the installed command directly:

```sh
source .venv/bin/activate
afl-scraper --help
```

For development, install the development dependency group and run the test suite:

```sh
uv sync --dev
uv run pytest
```

## Database setup

The scraping-only and mapping-file commands can run without PostgreSQL. Match loading, player transforms and pipelines, mapping upserts, and `dbcheck` require a configured database.

Set the following environment variables:

```sh
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=aflscraper_db
export DB_USER_OWNER=aflscraper_owner
export DB_PASSWORD_OWNER='owner-password'
export DB_USER_APP=aflscraper_app
export DB_PASSWORD_APP='app-password'
```

`DB_PORT` is optional and defaults to `5432`. The owner account is used for migrations and write operations; the app account is used for the read connection check.

For a new local PostgreSQL instance, the included bootstrap script creates the default database and roles. Run it as a PostgreSQL administrator, then apply the migrations:

```sh
psql -d postgres \
  --set=DB_PASSWORD_OWNER="$DB_PASSWORD_OWNER" \
  --set=DB_PASSWORD_APP="$DB_PASSWORD_APP" \
  --file=afl_scraper/storage/bootstrap.sql

uv run alembic upgrade head
uv run afl-scraper dbcheck
```

If you use existing roles or a differently named database, create and grant them yourself, set the corresponding environment variables, and run only the Alembic command. See [`afl_scraper/storage/README.md`](afl_scraper/storage/README.md) for schema development and migration conventions.

## CLI overview

All examples below use `uv run afl-scraper`. If the virtual environment is active, omit `uv run`.

| Command | What it does | PostgreSQL required |
| --- | --- | --- |
| `health` | Launches headless Chromium and verifies that the player-data source is reachable. | No |
| `smoke` | Checks that expected fixture controls still exist at the match-data source. | No |
| `dbcheck` | Tests both the owner/write and app connections and reports the PostgreSQL version. | Yes |
| `scrape players YEAR` | Saves raw player records under `data/raw/`. | No |
| `scrape match ID` | Scrapes, transforms, and loads one match and its player statistics. | Yes |
| `scrape round ROUND` | Processes every match in a round; use `--no-load` for extraction only. | Unless `--no-load` is used |
| `transform players` | Transforms stored player records and loads the resulting player models. | Yes |
| `pipeline players` | Runs the player transform/load pipeline, optionally refreshing raw pages first. | Yes |
| `map scrape` | Saves player identity data from each configured source to `data/mapping/`. | No |
| `map match` | Produces exact, reviewable, and unmatched cross-source player ID groups. | No |
| `map review` | Interactively reviews mappings and writes an approved mapping file. | No |
| `map upsert` | Upserts an approved mapping file into PostgreSQL. | Yes |

Run `uv run afl-scraper COMMAND --help` for the options accepted by any command or command group.

## Common workflows

### Check the installation

These commands exercise the browser, upstream sources, and database independently:

```sh
uv run afl-scraper health
uv run afl-scraper smoke
uv run afl-scraper dbcheck
```

Pass `--no-headless` to browser-based commands when you need to watch or debug the browser session:

```sh
uv run afl-scraper smoke --no-headless
```

### Scrape and load player data

Scrape player records for a season without touching the database:

```sh
uv run afl-scraper scrape players 2026
```

Transform the stored pages and load them into PostgreSQL:

```sh
uv run afl-scraper transform players
```

The full pipeline combines those steps. By default it reuses the raw pages already on disk; add `--scrape` to refresh them first:

```sh
uv run afl-scraper pipeline players --year 2026
uv run afl-scraper pipeline players --scrape --year 2026
```

### Scrape matches

Load one match by its source match ID:

```sh
uv run afl-scraper scrape match 6994
```

Process a complete home-and-away round:

```sh
uv run afl-scraper scrape round 1 --year 2026
```

Round identifiers are strings, so special rounds and finals can use fixture labels such as `OR`, `QF`, `SF`, `PF`, or `GF`:

```sh
uv run afl-scraper scrape round OR --year 2026
```

To scrape a round without loading its transformed records into PostgreSQL:

```sh
uv run afl-scraper scrape round 1 --year 2026 --no-load
```

The round pipeline isolates match failures: it reports an error for the affected match and continues processing the remaining fixture.

### Map player IDs across sources

The mapping workflow connects player identifiers across the configured sources:

```sh
uv run afl-scraper map scrape --year 2026
uv run afl-scraper map match --year 2026
uv run afl-scraper map review --year 2026
uv run afl-scraper map upsert --year 2026
```

The steps create ignored local source, review, and approval files under `data/mapping/`:

1. One source file for each configured provider
2. `data/mapping/2026_to_review.json`
3. `data/mapping/2026_approved.json`

AFL Official team pages expose current rosters only, so `map scrape` rejects a
historical `--year` rather than labeling current players as historical data. The
Official scrape requires plausible, unique rosters from all 18 clubs. Snapshot
writes reject empty, duplicate, or wrong-year records and atomically replace the
last-known-good file.

`map review` auto-approves exact name-and-team matches, prompts for ambiguous matches, and lets you decide whether unmatched players should be retained without a corresponding cross-source ID. Use `--input PATH` with `map review` or `map upsert` to supply a non-default JSON file.

## Data and architecture

The application is split into four main layers:

- `afl_scraper/scraper/` controls Playwright, navigates source sites, parses pages, and stores raw files.
- `afl_scraper/transform/` and `afl_scraper/transformer/` normalise source data into Pydantic domain models.
- `afl_scraper/pipelines/` orchestrates extract, transform, and load workflows.
- `afl_scraper/storage/` manages PostgreSQL connections, SQL table definitions, migrations, and idempotent model saves.

Generated data under the root `data/` directory is intentionally excluded from Git. Match scraping also retains captured player-stat HTML under `afl_scraper/data/raw/match/<match-id>/` for inspection.

Team and venue names from source sites are normalised before database loading. Venue aliases are maintained in `config/venue_name_mappings.jsonc`; update that file when a source introduces a venue name the transformer does not recognise.

## Tooling

- Playwright for browser automation and JavaScript-rendered pages
- Beautiful Soup and pandas for parsing and tabular transformations
- Pydantic for validated domain models
- Click for the command-line interface
- psycopg and PostgreSQL for persistence
- Alembic for SQL-first schema migrations
- pytest and Black for testing and formatting
