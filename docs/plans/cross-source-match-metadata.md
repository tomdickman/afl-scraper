# Cross-source AFL match metadata recovery

## Problem

Some historical AFL Match Centre pages still expose player statistics but do not
render the match header. Match 292 is a confirmed example: the page has no
`.mc-header__date-wrapper`, and the timeline and score widgets contain placeholder
values. The current parser cannot use the otherwise available player table because
match details extraction and team-stat extraction both derive the competition year
from that missing header.

The affected fields are not safe to infer from player statistics. A fallback must
recover the round, teams, date, local start time, venue, and final score from a
separately cached source, then prove that record belongs to the official match ID.

For match 292, AFL Tables publishes a unique 2013 record with:

- Round 5
- St Kilda v Sydney
- 25 April 2013 at 7:50 PM local time
- Wellington
- St Kilda 9.9 (63), Sydney 11.13 (79)

Sources used during this investigation:

- AFL Match Centre: https://www.afl.com.au/afl/matches/292
- AFL Tables match: https://afltables.com/afl/stats/games/2013/151620130425.html
- AFL Tables 2013 season: https://afltables.com/afl/seas/2013.html
- AFL 2013 fixture context: https://www.afl.com.au/news/471046/st-kilda-2013-fixture

## Design principles

1. AFL Official remains the source for player IDs and detailed player statistics.
2. The official season manifest anchors the official match ID, year, round, and
   fixture membership.
3. AFL Tables is the first metadata cross-check and fallback because its season
   page and match page expose the required details for this gap.
4. A fallback is allowed only when a unique external record matches the official
   fixture identity. No fuzzy match or first-result selection is allowed.
5. Complete official metadata remains preferred, but it is cross-checked against
   the external record. A disagreement is an error, not a silent overwrite.
6. Raw source evidence and provenance are retained beside the combined cache.
7. Existing cache envelopes remain readable; fallback caches use a versioned
   provenance extension.

## Proposed implementation

### 1. Inventory the gap before changing extraction

Add a read-only `audit match-metadata --year YEAR` command that visits or inspects
each manifest member and classifies it as:

- complete official header;
- missing official header;
- partial or malformed official header;
- official/external agreement;
- official/external conflict;
- no unique external candidate.

Write an atomic report under `data/reports/match_metadata/<year>.json`. This gives
the feature a bounded rollout list and distinguishes the known legacy gap from a
new upstream outage.

### 2. Introduce a metadata-source contract

Create a match-metadata adapter interface separate from the existing player-source
interface. It should return a source-native record containing:

- source name and source match URL/ID;
- season year and round;
- ordered home and away teams;
- local date and time;
- source venue name;
- goals, behinds, and total for both teams;
- retrieval timestamp.

Implement an AFL Tables adapter that:

- downloads and retains the raw season HTML;
- parses every match and its match-stat link from `/afl/seas/<year>.html`;
- optionally loads the linked match page for confirmation;
- validates score arithmetic and uniqueness;
- atomically writes a year catalogue under
  `data/raw/afl_tables/season/<year>/matches.json`.

Discover AFL Tables links from the season page; do not construct or reverse-engineer
its match IDs.

### 3. Enrich the official season manifest

Introduce a backward-compatible manifest schema version that can retain the
fixture facts available during official season discovery: round, official match
ID, ordered teams, scheduled date/time, and venue where present. Keep version 1
manifests readable and provide an explicit refresh path to acquire richer fixture
records.

The official fixture record is the bridge between official match ID 292 and an
external match. Direct single-match scraping should accept `--year` or resolve the
ID from a local season manifest; it should not search all seasons heuristically.

### 4. Match records deterministically

Resolve an external candidate using all available identity fields:

1. exact season;
2. canonical ordered home and away teams;
3. exact local calendar date;
4. normalized round label;
5. canonical venue when the fixture exposes it;
6. exact goals, behinds, and totals when both sources expose scores.

Team and venue comparisons use the existing source-specific mapping functions.
Require exactly one candidate. Zero or multiple candidates fail with a bounded
diagnostic showing the compared fields and candidate source URLs.

For match 292 this should resolve the AFL Tables record above through 2013,
Round 5, St Kilda v Sydney, and 25 April—not through score similarity alone.

### 5. Decouple details from player-stat extraction

Refactor the current page parser into two independent operations:

- `extract_official_match_details(page)` returns complete details, a typed
  `metadata unavailable` result when the entire legacy header is absent, or an
  error for a partial/malformed header;
- `extract_official_player_stats(page, expected_year)` receives the manifest year
  explicitly and never reads `.mc-header__date-wrapper`.

Pass the manifest year into `select_team_stats` and competition-rule validation.
This allows the official player table to be retained even when metadata is
recovered elsewhere.

Fallback must trigger only for the recognized absent-header condition. Selector
drift, a partially rendered header, an incomplete live page, or invalid official
values must continue to fail closed.

### 6. Normalize local time explicitly

AFL Tables can show both venue-local time and a parenthesized Australian time.
Treat the first time as venue-local and resolve its UTC offset using the canonical
venue and match date through `zoneinfo`. Expand `venue_timezones.jsonc` so every
fallback-capable canonical venue has an IANA timezone, including
`Wellington: Pacific/Auckland`.

Convert the result to the existing date/time representation only at the current
model boundary. A later model revision may store an aware datetime directly, but
that is not required for the fallback.

### 7. Record provenance without losing raw data

Extend `CachedRawMatch` with a backward-compatible provenance object containing:

- player-stat source and URL;
- metadata source and URL;
- official fixture evidence used for identity resolution;
- fields supplied by each source;
- cross-check outcome and timestamp.

Retain the AFL Official captures and the AFL Tables raw HTML beside the match
cache. Promote `match.json` only after source parsing, deterministic matching,
cross-checking, and the existing `RawMatchData` validation all succeed.

### 8. Conflict and availability policy

- Official complete + AFL Tables equal: use official details and record agreement.
- Official header absent + unique fixture/AFL Tables match: use AFL Tables details.
- Official partial: fail; do not fill individual blanks silently.
- Official and AFL Tables disagree: fail with a field-level comparison.
- AFL Tables unavailable with an existing validated fallback cache: reuse and
  revalidate the cache.
- AFL Tables unavailable without a cache: fail and leave no promoted match cache.
- No unique candidate: fail and require a reviewed mapping override.

Add an optional reviewed override file keyed by official match ID only for genuine
source-identity ambiguities. Overrides identify the external source record; they
must never contain hand-entered match facts.

## Test plan

Add saved HTML fixtures and unit tests for:

- match 292 with player stats present and the complete official header absent;
- complete official metadata agreeing with AFL Tables;
- complete official metadata conflicting on one field;
- partial official header refusing fallback;
- zero and multiple AFL Tables candidates;
- home/away order mismatch;
- round and venue alias normalization;
- score arithmetic and score disagreement;
- Wellington local time and daylight-saving behavior;
- atomic source catalogue and match-cache promotion;
- offline reuse of validated fallback evidence;
- backward loading of existing schema-version-1 match caches;
- direct match scraping with and without a resolvable season context.

Run a cache-only preflight over every configured official season before enabling
fallback by default. The rollout report must enumerate every fallback match and
show zero unresolved or conflicting records.

## Delivery sequence

1. Add inventory/reporting and HTML fixtures.
2. Add the AFL Tables metadata adapter and year catalogue.
3. Enrich official manifests and add deterministic cross-source matching.
4. Decouple official player-stat parsing from header parsing.
5. Add provenance-aware cache schema and fallback orchestration.
6. Backfill and review all configured official seasons offline.
7. Enable fallback in `scrape all` and the season mapping workflow.
8. Document operator diagnostics, refresh behavior, and reviewed overrides.

## Acceptance criteria

- Match 292 produces one validated raw cache using AFL Official player statistics
  and AFL Tables metadata with explicit provenance.
- A fallback cannot be selected by score, team name, or date alone.
- Conflicting sources never produce a promoted cache.
- Existing valid caches and manifests remain readable.
- Database code is never opened by scraping or metadata audit commands.
- A complete configured-season preflight reports every metadata source and no
  unresolved match identities.
