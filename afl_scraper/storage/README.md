# AFL Scraper - Storage

Module responsible for loading data into various locations for use.

## Environment variables

Connection stings refer to required environment variables which are expected to be present, they are:

`DB_NAME`: The database name
`DB_HOST`: The hostname of the database
`DB_PASSWORD_APP`: The password for the database app (consumer) connection
`DB_PASSWORD_OWNER`: The password for the database owner (required for migrations)
`DB_USER_APP`: The user name of the database app (consumer) connection
`DB_USER_OWNER`: The user name of the database owner (required for migrations)

## RBDMS

We use Postgres for relational data, the schema and migrations are managed with an SQL first approach, not using models or an ORM.
This allows for the writing of custom and performant SQL, without the limitations or potential issues of an ORM.

### Migrations

Any changes to the database need to be managed through a migration, these are managed via `alembic` and can be created with:

```sh
alembic revision -m "migration description"
```

This will create a migration file under [./migrations/versions](./migrations/versions/) with a name like `c86df_migration_description.py`
You then need to manually create `upgrade` and `downgrade` steps in the created file, to allow for idempotent migrations.
Any SQL to be run should be added to [./tables](./tables/) and referred to by the appropriate migration script.
If you create an SQL file, __DO NOT duplicate SQL inside the migrations.__

Following this run:

```sh
alembic upgrade head
```

If successful, an entry will be created in the `alembic_version` table like so:

```sql
aflscraper_db=# SELECT * FROM alembic_version;
 version_num
--------------
 c6230ed6782e
(1 row)
```
