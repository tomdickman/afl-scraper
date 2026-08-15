# AFL Scraper - Scraper

This module is responsible for fetching required pages, navigating within pages and parsing raw data from within the page without any transformations or storage.

All CSS selectors and other site structure information is maintained within this module.

## Historical source coverage

The career-history target starts with the 2006 season. Coverage is intentionally
tracked separately for each source because the sources do not expose the same
historical range.

| Source contract | Reviewed range | Validation |
| --- | --- | --- |
| AFL Tables player-season lists | 2006-2026 | Exact club set for the 16-, 17-, and 18-club competition eras, plausible per-club roster sizes, and unique player IDs |
| AustralianFootball season indexes | 2006-2011 | Reviewed complete match totals of 185, 185, 185, 185, 186, and 196; unique match IDs across home-and-away rounds and finals |
| AustralianFootball match pages | Sampled in 2006 and 2011 | Match metadata and score invariants, exact core-stat headers, 22 players per team, stable source player IDs, and disposal totals |
| AFL Official fixture catalogue | 2012-2026 | Explicit reviewed season IDs; discovered round labels and match IDs are written to a validated manifest |
| AFL Official completed match pages | Sampled in 2012, 2020, and 2025 | Completed status, scores, required stat headers, source player IDs, and season-specific 22/23-player match-day teams |

The public AFL Official competition-season catalogue exposes no Premiership
season before 2012. AustralianFootball provides the separate 2006-2011 match
boundary: season indexes enumerate every match, and match pages expose stable
source player IDs plus the core published statistics. Unpublished advanced
statistics remain unavailable rather than being inferred or zero-filled.

AustralianFootball data is cached in source-specific models. Its player IDs are
not AFL Official or AFL Tables IDs, and therefore cannot enter the existing load
pipeline until an explicit canonical mapping has been reviewed. AFL Tables is
not a runtime dependency of historical season discovery or match caching.

The reviewed constants are bounded at the latest configured season. Additions or
future competition changes require updating the season catalogue and competition
rules together with source-contract tests.

Validated match JSON is the resumable boundary for historical identity work. A
historical player snapshot is promoted only after every match in the season
manifest has been loaded from a valid cache or successfully scraped, all matches
agree with the requested year, and each repeated official ID retains one name and
team identity. Source snapshots for official participants and AFL Tables players
are then promoted together.
