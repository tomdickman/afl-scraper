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

The complete raw-data and database workflows cover 2006 through 2026. AFL Tables provides
player seasons, profiles, match metadata, and statistics across that range;
AustralianFootball provides an independent match source across the same range;
and the reviewed AFL Official fixture catalogue covers 2012 through 2026.
Generic season commands route 2006-2011 through AustralianFootball and
2012-2026 through AFL Official. AFL Tables validation covers the
16-club, 17-club, and 18-club competition eras.

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

For a local environment file, copy
`afl_scraper/storage/.env.example` to `afl_scraper/storage/.env`, replace every
placeholder, and restrict it to the current user:

```sh
chmod 600 afl_scraper/storage/.env
```

The CLI deliberately does not discover nested environment files implicitly.
Pass the file explicitly to `uv run`:

```sh
uv run --env-file afl_scraper/storage/.env afl-scraper dbcheck
uv run --env-file afl_scraper/storage/.env alembic upgrade head
```

The real `.env` file is ignored by Git; `.env.example` contains names and safe
placeholders only.

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
| `scrape all` | Resumably caches and validates every configured player and match source, plus team/venue audit catalogs. | No |
| `scrape season YEAR` | Discovers a provider-routed season and optionally caches every match. | No |
| `scrape match ID` | Scrapes, transforms, and loads one match and its player statistics. | Yes |
| `audit match-metadata --year YEAR` | Verifies every official fixture resolves to one AFL Tables metadata record and writes an atomic report. | No |
| `scrape round ROUND` | Processes every match in a round; use `--no-load` for extraction only. | Unless `--no-load` is used |
| `transform players` | Transforms stored player records and loads the resulting player models. | Yes |
| `pipeline players` | Prepares and optionally loads canonical players for any configured range. | Only with `--load` |
| `pipeline season YEAR` | Preflights and optionally loads any provider-routed cached season. | Yes |
| `pipeline backfill` | Preflights and optionally loads an inclusive 2006-2026 range. | Yes |
| `map scrape` | Derives source-qualified identities from any configured cached season. | No |
| `map match` | Produces exact, reviewable, and unmatched cross-source player ID groups. | No |
| `map review` | Interactively reviews mappings and writes an approved mapping file. | No |
| `map review-all` | Reviews every incomplete mapping year in one resumable interactive run. | No |
| `map upsert` | Upserts approved mapping files for one year or an inclusive range into PostgreSQL. | Yes |

Run `uv run afl-scraper COMMAND --help` for the options accepted by any command or command group.

## Common workflows

### Scrape every source without loading PostgreSQL

Run the complete configured 2006-2026 raw extraction with one command:

```sh
uv run afl-scraper scrape all
```

This command never opens a database connection. It validates and reuses existing
good caches, downloads only missing data, and can safely be rerun after an
interruption. It covers AFL Tables player snapshots, profiles, complete match
catalogues, and match-stat pages for every year; AustralianFootball season
indexes and all available match pages for every year; and AFL Official fixtures
and matches for 2012-2026. Reviewed AustralianFootball source omissions and the
cancelled 2015 Adelaide-Geelong fixture remain explicit records rather than
being represented by invented match or player data. The browser is visible by
default because AustralianFootball may reject a fresh headless session.

The resulting files are grouped beneath `data/`:

- `data/raw/afl_tables/player/` contains the deduplicated raw player profiles.
- `data/raw/afl_tables/match/` contains every validated match-stat page.
- `data/mapping/<year>_afl_tables.json` contains each AFL Tables season roster.
- `data/raw/australian_football/` contains source manifests, available match
  HTML, validated match JSON, and reviewed cancellation or source-omission
  records.
- `data/raw/afl_official/` contains 2012-2026 manifests, captured player-stat
  HTML, and validated match JSON.
- `data/mapping/<year>_<source>.json` contains the participating players derived
  from the complete match cache.
- `data/raw/catalog/<year>/<source>.json` lists every observed source team and
  venue next to its canonical mapping. `data/raw/catalog/<year>.json` is the
  combined coverage manifest: each potential source is explicitly marked
  `complete` or `unavailable`, with its data types, counts, cache path, and
  cross-source validation result. `data/raw/catalog/2006-2026-report.json`
  summarizes the complete run.

Every available cached match is revalidated, including its scores and player
rows. Reviewed cancellations are retained as scheduled fixtures with no player
statistics, while reviewed source omissions are cross-checked against their
exact AFL Official and AFL Tables identities. The catalog phase also exercises
team aliases, venue aliases, match dates, and historical venue timezones. An
unreviewed omission or unknown or invalid value stops the command with the
affected source value, so no successful report is written for that year.
When two otherwise valid sources publish different metadata, the command emits
a warning and preserves the field-level differences in the year's
`cross_source_validations` manifest instead of discarding either source. Score
conflicts include each source's `goals * 6 + behinds` arithmetic and, when
available, AFL Official totals that identify which alternate source is the
outlier.

Use a smaller inclusive range while diagnosing a failure:

```sh
uv run afl-scraper scrape all --from-year 2012 --to-year 2012
```

Normal reruns should not use `--refresh`. That flag deliberately reacquires and
replaces every requested manifest, match, season snapshot, and player profile.
To force a complete 2006-2026 reacquisition and validation, run:

```sh
uv run afl-scraper scrape all \
  --from-year 2006 \
  --to-year 2026 \
  --refresh \
  --no-headless
```

Use `--headless` only when AustralianFootball accepts a fresh headless session;
that source is consulted throughout the configured range and may reject one.

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

The generic player pipeline validates the requested AFL Tables snapshots and
profiles before loading anything. It defaults to the complete configured range
and a dry run:

```sh
uv run afl-scraper pipeline players --offline
uv run afl-scraper pipeline players --offline --load
uv run afl-scraper pipeline players --from-year 2026 --to-year 2026 --offline
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

Load one match by its source match ID. Pass its season so legacy pages with a
missing match header can use the enriched manifest and cross-source metadata:

```sh
uv run afl-scraper scrape match 292 --year 2013
```

Player tables normally come from AFL Official. Its rerendering team dropdown is
selected without waiting on an option node that can detach from the DOM, then
the resulting roster is still validated. When the legacy player-stat view is
genuinely unavailable during a season scrape, the scraper uses the uniquely
matched AFL Tables record and maps every participant back to an official
identity anchored by profile links in the current or an earlier match. AFL
Fantasy points are calculated from the alternate source's published components;
unavailable metres-gained values remain null. Impossible official values, such
as an individual time-on-ground percentage outside 0-100, reject the complete
official player-stat dataset and select the complete alternate dataset rather
than clamping or mixing fields.
When only the official match header is absent, match details also come from the
matched AFL Tables record. Source URLs and compared fields are stored in the
versioned raw match cache, and the alternate HTML is retained under
`data/raw/afl_tables/match`. A partial source, unknown or ambiguous player,
ambiguous match identity, or source conflict fails without promoting a cache.
Complete official data is retained and cross-checked. Season scraping retains
the accumulated identities from every available completed earlier AFL Official
season, allowing a returning player to be resolved after one or more seasons
without a match appearance while still rejecting ambiguous identities.

Before scraping a season, validate all cross-source fixture identities without
opening PostgreSQL:

```sh
uv run afl-scraper audit match-metadata --year 2013
```

The command reuses `data/raw/afl_tables/season/2013/matches.json` when present
and writes `data/reports/match_metadata/2013.json`. Use `--refresh` to reacquire
the AFL Tables catalogue. If the season manifest predates the enriched schema,
rerun `scrape season 2013` first.

Process a complete home-and-away round:

```sh
uv run afl-scraper scrape round 1 --year 2026
```

Round identifiers are strings, so special rounds and finals can use fixture
labels such as `OR`, `WF`, `QF`, `EF`, `SF`, `PF`, or `GF`:

```sh
uv run afl-scraper scrape round OR --year 2026
```

Raw providers use several spellings for the same stage. The transform layer
stores only positive round numbers without a `Round` prefix, or the canonical
special-round values `OR`, `WF`, `QF`, `EF`, `SF`, `PF`, and `GF`. Combined
qualifying-and-elimination fixture labels such as `QE` and `Finals Week 1` are
not canonical stages. Each affected official match is resolved to `QF` or `EF`
only when its cached AFL Tables and AustralianFootball records agree; a missing
or conflicting classification stops the preflight before database writes.

To scrape a round without loading its transformed records into PostgreSQL:

```sh
uv run afl-scraper scrape round 1 --year 2026 --no-load
```

The round pipeline isolates match failures: it reports an error for the affected match and continues processing the remaining fixture.

After a completed season manifest, match caches, and player mappings exist,
validate and transform any complete season without writing:

```sh
uv run afl-scraper pipeline season 2025
```

The command resolves the configured source for the year, checks its complete
cache, year-scoped player mappings and database references, transforms every
match, and reports match and player-stat totals. Add `--load` to persist each
game and all of its statistics atomically and require exact reconciliation.

### Cache any season

The command resolves the canonical match source from the year. Seasons from
2006-2011 use AustralianFootball; seasons from 2012 onward use AFL Official.
Discover and validate a manifest without requesting every match page:

```sh
uv run afl-scraper scrape season 2006
```

This command defaults to a visible browser because the source currently returns
HTTP 403 to a fresh headless session. The scraper does not disguise its browser
identity or bypass that restriction.

After inspecting the manifest, cache the complete season. Existing valid caches
are reused, so rerunning the command safely resumes after a network or source
failure:

```sh
uv run afl-scraper scrape season 2006 --matches
```

The default 500 ms delay applies only between live match requests. Use
`--refresh` only when intentionally replacing every validated cache.

This extraction boundary deliberately retains AustralianFootball player IDs as
source-specific IDs. Match pages publish jumper number, kicks, marks, handballs,
disposals, goals, behinds, hitouts, tackles, and frees for/against. A jumper
number is retained as unavailable when the source leaves that player's cell
blank. Statistics the source does not publish are absent rather than recorded
as zero.

### Prepare canonical players

Before reviewing AustralianFootball identities, prepare the corresponding
year-scoped AFL Tables snapshots and canonical player records:

```sh
uv run afl-scraper pipeline players --offline
```

The safe default acquires only missing data, validates all six season snapshots
and every unique player profile, and performs no database writes. Each newly
validated snapshot and profile is retained as a resume boundary, so rerunning
after an interruption skips completed work. Requests have a default 500 ms
delay; use `--delay-ms` to increase it if the source is under load.

After the complete dry run succeeds, load the same validated caches:

```sh
uv run afl-scraper pipeline players --offline --load
```

The offline load performs no web requests and upserts all canonical players in
one transaction. Replaying it is idempotent. `--refresh` deliberately replaces
all requested snapshots and profiles, retaining the previous complete profile
cache if the refresh fails. It cannot be combined with `--offline`.

Use `--from-year` and `--to-year` for a smaller inclusive pilot, for example:

```sh
uv run afl-scraper pipeline players \
  --from-year 2006 --to-year 2006
```

### Map and load a cached season

Apply the source-qualified identity and nullable-stat migration first:

```sh
uv run alembic upgrade head
```

Mapping uses the AFL Tables player ID as the canonical database player ID and
keeps every provider ID source-qualified. The same commands select
AustralianFootball for 2006-2011 and AFL Official from 2012 onward:

```sh
uv run afl-scraper map match --year 2006
uv run afl-scraper map review --year 2006
uv run afl-scraper map upsert --year 2006 --require-complete
```

The upsert fails before opening a database connection if any participating
source ID is missing, unexpected, or aliases another canonical player. It also
fails through the database foreign key if a canonical player has not yet been
loaded.

Run the complete cache, mapping, team, venue, timezone and database-reference
preflight. This is the safe default and performs no writes:

```sh
uv run afl-scraper pipeline season 2006
```

After reviewing the counts, load the season explicitly:

```sh
uv run afl-scraper pipeline season 2006 --load
```

Provider match IDs are resolved through a source-qualified identity before an
internal game ID is allocated. Each game and all of its player rows are one
transaction. Replaying a season updates the same records, and null historical
fields do not erase richer values already stored for those records.
Reviewed cancelled fixtures remain part of scheduled-season coverage, but do
not require a match cache and are never transformed or loaded as played games.

### Run a multi-season backfill

After every year has complete caches and approved mappings, preflight the full
range before allowing any database writes:

```sh
uv run afl-scraper pipeline backfill --from-year 2006 --to-year 2026
```

The dry run validates the entire range before any write is possible. The
reconciliation checks identities, every canonical game field, participant
sets, and every statistic published by the historical source. Unpublished null
fields are ignored so independently enriched values remain valid.

Load the range only after reviewing the dry-run output:

```sh
uv run afl-scraper pipeline backfill \
  --from-year 2006 --to-year 2026 --load
```

All requested years must pass preflight before the first game is written. Each
game and its player rows are one transaction. A rerun skips seasons that already
reconcile completely and uses idempotent upserts for incomplete seasons.

### Map player IDs across sources

The mapping workflow connects player identifiers across the configured sources:

```sh
uv run afl-scraper map review-all
```

To approve every review item that has exactly one candidate while retaining
interactive prompts for ambiguous choices, run:

```sh
uv run afl-scraper map review-all --accept-single-candidate
```

`review-all` covers the configured 2006-2026 range in one interactive run. It
uses AustralianFootball participants for 2006-2011 and AFL Official participants
from 2012 onward, regenerates candidates from the validated local snapshots and
match caches, and skips any year whose approved file already has complete source
coverage. Each completed year is saved immediately, so an interrupted run can be
resumed with the same command. Previously approved official-source decisions in
an incomplete year are retained, while unresolved same-team players can be
paired explicitly when a source has changed or shortened a name. Use
`--from-year` and `--to-year` to limit the range, or `--force` to discard retained
decisions and deliberately review a year again. `--accept-single-candidate` is
explicitly opt-in and never selects among two or more candidates. The command
does not connect to PostgreSQL or upsert any mappings.

The individual commands remain available when working on one year:

```sh
uv run afl-scraper map scrape --year 2026
uv run afl-scraper map match --year 2026
uv run afl-scraper map review --year 2026
uv run afl-scraper map upsert --year 2026
```

After reviewing several seasons, upsert the complete inclusive range in one
command:

```sh
uv run afl-scraper map upsert \
  --from-year 2012 \
  --to-year 2026 \
  --require-complete
```

Every approved file, and every source snapshot when `--require-complete` is
used, is validated before the database connection is opened. The range is then
written through one connection so a failure does not commit only part of the
requested range. `--year` remains available for a single season and defaults to
the current year when no year options are supplied. `--input` is supported only
for single-year upserts because range mode resolves each year's default approved
file.

The steps create ignored local source, review, and approval files under `data/mapping/`:

1. One source file for each configured provider
2. `data/mapping/2026_to_review.json`
3. `data/mapping/2026_approved.json`

`map scrape` derives identities from the completed season cache selected by the
year-routing policy, rather than labeling current rosters as historical data.
Snapshot writes reject empty, duplicate, or wrong-year records and atomically
replace the last-known-good file.

For a completed season in the reviewed 2012-2026 official fixture range, first
discover its manifest and then derive identities from the completed match pages.
This includes the current calendar year once its final match is complete:

```sh
uv run afl-scraper scrape season 2012 --matches
uv run afl-scraper map scrape --year 2012
uv run afl-scraper map match --year 2012
uv run afl-scraper map review --year 2012
uv run afl-scraper map upsert --year 2012 --require-complete
```

Each fully validated match is cached as
`data/raw/afl_official/match/<match-id>/match.json`. Subsequent mapping runs reuse
that cache; pass `--refresh` to reacquire every page deliberately. Invalid cached
JSON fails closed rather than being silently replaced.

Season identities are the union of players who actually appeared in the
selected source manifest. Repeated source IDs must retain the same normalized
name, team, and year across every match. Benign punctuation, suffix, and
middle-initial differences can match exactly when the team also agrees.
Nickname differences remain interactive review items using same-team,
same-surname candidates.

Use `--require-complete` when upserting match-derived mappings. For either a
single year or a range, it verifies that every participating source ID has an
approved canonical mapping before opening a database connection. Individual
match loading retains its existing mapping coverage check as a second guard.

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
