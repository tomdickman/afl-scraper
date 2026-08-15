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
| AFL Official fixture catalogue | 2012-2026 | Explicit reviewed season IDs; discovered round labels and match IDs are written to a validated manifest |
| AFL Official completed match pages | Sampled in 2012, 2020, and 2025 | Completed status, scores, required stat headers, source player IDs, and season-specific 22/23-player match-day teams |

The public AFL Official competition-season catalogue exposes no Premiership
season before 2012. Consequently, 2006-2011 player lists are supported but match
discovery and player-game statistics still require a separate historical match
source. Commands fail explicitly at that boundary rather than relabeling or
silently omitting those seasons.

The reviewed constants are bounded at the latest configured season. Additions or
future competition changes require updating the season catalogue and competition
rules together with source-contract tests.
