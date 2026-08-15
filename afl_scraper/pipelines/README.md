# Pipelines

This module contains pipelines for orchestrating data lifecycles, utilising the `scraper`, `transform` and `storage` modules to extract data, transform it into known structures and then loading it into a database for use.

The historical-season pipeline is cache-only: scraping is a separate operator
step. It preflights the complete season before writes and defaults to dry-run.
When loading is explicit, each game and all player statistics share one database
transaction, allowing a failed run to resume safely without partial matches.
