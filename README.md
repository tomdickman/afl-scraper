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

The reviewed AFL Official fixture catalogue covers 2012 through 2026. AFL Tables
player-season validation covers the required career-history range from 2006,
including the 16-club, 17-club, and 18-club competition eras. The AFL Official
catalogue does not expose 2006-2011, so those matches require a historical source
adapter before they can be backfilled.

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

### Reset a disposable development database

To discard all PostgreSQL data and Alembic state in a local development
database, then rebuild it from the migrations in the current checkout, run:

```sh
uv run afl-scraper database reset
```

The command displays the resolved target and requires its exact database name
as confirmation. It refuses non-loopback hosts and PostgreSQL system databases.
It drops and recreates only the target database's `public` schema, restores the
restricted app-role access configured by `bootstrap.sql`, and migrates to
`head`. It does not delete roles, the database itself, or cached and reviewed
files under `data/`.

For an intentionally empty schema, use `--no-migrate`. For a non-interactive
development script, pass the same value as `DB_NAME` explicitly:

```sh
uv run afl-scraper database reset --confirm-database "$DB_NAME"
```

## CLI overview

All examples below use `uv run afl-scraper`. If the virtual environment is active, omit `uv run`.

| Command | What it does | PostgreSQL required |
| --- | --- | --- |
| `health` | Launches headless Chromium and verifies that the player-data source is reachable. | No |
| `smoke` | Checks that expected fixture controls still exist at the match-data source. | No |
| `dbcheck` | Tests both the owner/write and app connections and reports the PostgreSQL version. | Yes |
| `database reset` | Clears and rebuilds a disposable local PostgreSQL database. | Yes |
| `scrape players YEAR` | Saves raw player records under `data/raw/`. | No |
| `scrape season YEAR` | Discovers every source round and match ID and writes a validated season manifest. | No |
| `scrape historical-season YEAR` | Discovers AustralianFootball matches from 2006-2011 and optionally caches every validated match page. | No |
| `scrape match ID` | Scrapes, transforms, and loads one match and its player statistics. | Yes |
| `scrape round ROUND` | Processes every match in a round; use `--no-load` for extraction only. | Unless `--no-load` is used |
| `transform players` | Transforms stored player records and loads the resulting player models. | Yes |
| `pipeline players` | Runs the player transform/load pipeline, optionally refreshing raw pages first. | Yes |
| `pipeline prepare-historical-players` | Prepares validated AFL Tables snapshots and canonical players for 2006-2011. | Only with `--load` |
| `map scrape` | Saves player identity data from each configured source to `data/mapping/`. | No |
| `map scrape-season` | Derives participating historical official IDs from every match in a completed season. | No |
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

A fresh AFL Tables extraction is staged separately and replaces the cached player
directory only after every expected page passes validation. An unavailable,
redirected, incomplete, or malformed source stops the pipeline before cached data
is transformed or loaded. Season-specific structural checks support AFL Tables
player lists from 2006 onward: 16 clubs in 2006-2010, 17 in 2011, and 18 from
2012. The 2006-2007 source name `Kangaroos` is also validated explicitly.

### Scrape matches

Discover the source-defined round labels and match IDs before processing a
season:

```sh
uv run afl-scraper scrape season 2012
```

This writes `data/raw/afl_official/season/2012/manifest.json` atomically. It
rejects blank or duplicate rounds, invalid IDs, empty rounds, and any match ID
that appears in more than one round. Seasons before 2012 fail with an explicit
source-coverage error instead of being sent to the current fixture site.

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

### Cache the 2006-2011 historical source

AustralianFootball is the independent historical match source for 2006-2011.
Discover and validate a season without requesting every match page:

```sh
uv run afl-scraper scrape historical-season 2006
```

This command defaults to a visible browser because the source currently returns
HTTP 403 to a fresh headless session. The scraper does not disguise its browser
identity or bypass that restriction.

After inspecting the manifest, cache the complete season. Existing valid caches
are reused, so rerunning the command safely resumes after a network or source
failure:

```sh
uv run afl-scraper scrape historical-season 2006 --matches
```

The default 500 ms delay applies only between live match requests. Use
`--refresh` only when intentionally replacing every validated cache.

This extraction boundary deliberately retains AustralianFootball player IDs as
source-specific IDs. Match pages publish jumper number, kicks, marks, handballs,
disposals, goals, behinds, hitouts, tackles, and frees for/against. Statistics
the source does not publish are absent rather than recorded as zero.

### Prepare canonical players for 2006-2011

Before reviewing AustralianFootball identities, prepare the corresponding
year-scoped AFL Tables snapshots and canonical player records:

```sh
uv run afl-scraper pipeline prepare-historical-players
```

The safe default acquires only missing data, validates all six season snapshots
and every unique player profile, and performs no database writes. Each newly
validated snapshot and profile is retained as a resume boundary, so rerunning
after an interruption skips completed work. Requests have a default 500 ms
delay; use `--delay-ms` to increase it if the source is under load.

After the complete dry run succeeds, load the same validated caches:

```sh
uv run afl-scraper pipeline prepare-historical-players --offline --load
```

The offline load performs no web requests and upserts all canonical players in
one transaction. Replaying it is idempotent. `--refresh` deliberately replaces
all requested snapshots and profiles, retaining the previous complete profile
cache if the refresh fails. It cannot be combined with `--offline`.

Use `--from-year` and `--to-year` for a smaller inclusive pilot, for example:

```sh
uv run afl-scraper pipeline prepare-historical-players \
  --from-year 2006 --to-year 2006
```

### Map and load a cached 2006-2011 season

Apply the source-qualified identity and nullable-stat migration first:

```sh
uv run alembic upgrade head
```

Historical loading uses the AFL Tables player ID as the existing canonical
database player ID, but never treats an AustralianFootball numeric ID as the
same namespace. Generate conservative candidates from the complete match cache
and an existing `data/mapping/<year>_afl_tables.json` snapshot, review ambiguous
names, and require exact season coverage when saving the approved mappings:

```sh
uv run afl-scraper map match-historical --year 2006
uv run afl-scraper map review-historical --year 2006
uv run afl-scraper map upsert-historical --year 2006
```

The upsert fails before opening a database connection if any participating
source ID is missing, unexpected, or aliases another canonical player. It also
fails through the database foreign key if a canonical player has not yet been
loaded.

Run the complete cache, mapping, team, venue, timezone and database-reference
preflight. This is the safe default and performs no writes:

```sh
uv run afl-scraper pipeline historical-season 2006
```

After reviewing the counts, load the season explicitly:

```sh
uv run afl-scraper pipeline historical-season 2006 --load
```

Provider match IDs are resolved through a source-qualified identity before an
internal game ID is allocated. Each game and all of its player rows are one
transaction. Replaying a season updates the same records, and null historical
fields do not erase richer values already stored for those records.

### Run the resumable 2006-2011 backfill

After every year has complete caches and approved mappings, preflight the full
range before allowing any database writes:

```sh
uv run afl-scraper pipeline historical-backfill
```

The dry run validates all six years and writes two ignored, atomic artifacts:

- `data/checkpoints/australian_football/2006-2011.json` records per-year state.
- `data/reports/australian_football/2006-2011.json` compares expected caches
  with source-qualified database games and player statistics.

The reconciliation checks identities, every canonical game field, participant
sets, and every statistic published by the historical source. Unpublished null
fields are ignored so independently enriched values remain valid.

Load the range only after reviewing the dry-run output:

```sh
uv run afl-scraper pipeline historical-backfill --load
```

All requested years must pass preflight before the first game is written. After
each completed year, the checkpoint and reconciliation report are atomically
replaced. A rerun resumes by skipping only years that reconcile completely with
the database; the checkpoint file alone is never trusted. If a previously
completed year has drifted, resume fails closed. Inspect the report, then use
`--reprocess` only when deliberately repairing it with idempotent upserts:

```sh
uv run afl-scraper pipeline historical-backfill --load --reprocess
```

Use `--from-year` and `--to-year` for a smaller inclusive range. Custom artifact
locations are available through `--checkpoint` and `--report`.

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

For a completed historical season in the reviewed 2012-2026 official fixture
range, first discover its manifest and then derive identities from the completed
match pages:

```sh
uv run afl-scraper scrape season 2012
uv run afl-scraper map scrape-season --year 2012
uv run afl-scraper map match --year 2012
uv run afl-scraper map review --year 2012
uv run afl-scraper map upsert --year 2012 --require-complete
```

Each fully validated match is cached as
`data/raw/afl_official/match/<match-id>/match.json`. Subsequent mapping runs reuse
that cache; pass `--refresh` to reacquire every page deliberately. Invalid cached
JSON fails closed rather than being silently replaced.

Historical identities are the union of players who actually appeared in the
season manifest. Repeated official IDs must retain the same normalized name,
team, and year across every match. Benign punctuation, suffix, and middle-initial
differences can match exactly when the team also agrees. Nickname differences
remain interactive review items using same-team, same-surname candidates.

Use `--require-complete` when upserting match-derived mappings. It verifies that
every participating official ID has an approved canonical mapping before opening
a database connection. Individual match loading retains its existing mapping
coverage check as a second guard.

When reachable, the AFL Tables mapping source likewise requires all expected team
sections, plausible player counts, valid unique identifiers, and complete names.
It is not used to discover or scrape the AustralianFootball historical match
cache. Both identity snapshots must pass before either year-scoped mapping
snapshot is promoted.

`map review` auto-approves exact name-and-team matches and prompts for ambiguous
matches. Unmatched canonical players require no source-identity row. Use
`--input PATH` with `map review` or `map upsert` to supply a non-default JSON
file.

## Data and architecture

The application is split into four main layers:

- `afl_scraper/scraper/` controls Playwright, navigates source sites, parses pages, and stores raw files.
- `afl_scraper/transform/` and `afl_scraper/transformer/` normalise source data into Pydantic domain models.
- `afl_scraper/pipelines/` orchestrates extract, transform, and load workflows.
- `afl_scraper/storage/` manages PostgreSQL connections, SQL table definitions, migrations, and idempotent model saves.

Generated data under the root `data/` directory is intentionally excluded from Git. Match scraping also retains captured player-stat HTML under `data/raw/afl_official/match/<match-id>/` for inspection.

Team and venue names from source sites are normalised before database loading. Venue aliases are maintained in `config/venue_name_mappings.jsonc`; update that file when a source introduces a venue name the transformer does not recognise.

## Tooling

- Playwright for browser automation and JavaScript-rendered pages
- Beautiful Soup and pandas for parsing and tabular transformations
- Pydantic for validated domain models
- Click for the command-line interface
- psycopg and PostgreSQL for persistence
- Alembic for SQL-first schema migrations
- pytest and Black for testing and formatting
