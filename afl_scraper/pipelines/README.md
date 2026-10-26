# Pipelines

This module contains pipelines for orchestrating data lifecycles, utilising the `scraper`, `transform` and `storage` modules to extract data, transform it into known structures and then loading it into a database for use.

Season routing is centralized by year: AustralianFootball supplies canonical
matches for 2006-2011 and AFL Official supplies them from 2012 onward. Public
commands operate on years and ranges rather than exposing provider-specific
pipelines.

The generic season pipeline revalidates every manifest-member cache, resolves
year-scoped canonical player mappings, transforms every match with placeholder
internal IDs, and checks player, team, and venue references. Dry-run is the
default and performs no writes.

When loading is explicit, each game and all player statistics share one database
transaction. Source-qualified game identities make reruns idempotent. Exact
post-load reconciliation checks game fields, participant sets, and every
available statistic.

The generic backfill pipeline preflights an entire inclusive 2006-2026 range
before the first database write. Seasons that already reconcile are skipped;
incomplete seasons are loaded and reconciled before the next season proceeds.

The player pipeline builds canonical prerequisites for any configured range. It
validates year-scoped AFL Tables snapshots, deduplicates
profiles across seasons, resumes from each validated immutable cache, and opens
the database only after the complete requested range passes preflight. A load
upserts every canonical player in one transaction.
