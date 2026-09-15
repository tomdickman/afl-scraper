# Pipelines

This module contains pipelines for orchestrating data lifecycles, utilising the `scraper`, `transform` and `storage` modules to extract data, transform it into known structures and then loading it into a database for use.

The AFL Official season cache preflight is a read-only boundary for future
season loading. It revalidates every manifest-member cache, reports missing or
same-season unexpected matches, and rejects wrong-year data or player identity
drift without opening a browser or database connection.

The historical-season pipeline is cache-only: scraping is a separate operator
step. It preflights the complete season before writes and defaults to dry-run.
When loading is explicit, each game and all player statistics share one database
transaction, allowing a failed run to resume safely without partial matches.

The historical-backfill pipeline preflights an entire inclusive range before
the first database write. It stores atomic per-year checkpoints but confirms
them against exact database reconciliation before skipping work. Interrupted
runs therefore resume after the last reconciled year without treating local
checkpoint state as authoritative.

The historical-player preparation pipeline builds the canonical prerequisites
for that backfill. It validates year-scoped AFL Tables snapshots, deduplicates
profiles across seasons, resumes from each validated immutable cache, and opens
the database only after the complete requested range passes preflight. A load
upserts every canonical player in one transaction.
