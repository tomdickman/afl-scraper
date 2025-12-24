-- ============================================================
-- Load passwords from shell environment into psql variables
-- ============================================================

\set AFLSCRAPER_OWNER_DB_PASSWORD :'DB_PASSWORD_OWNER'
\set AFLSCRAPER_APP_DB_PASSWORD   :'DB_PASSWORD_APP'

-- Fail fast if variables are missing
\if :{?AFLSCRAPER_OWNER_DB_PASSWORD}
\else
  \echo 'ERROR: DB_PASSWORD_OWNER is not set'
  \quit 1
\endif

\if :{?AFLSCRAPER_APP_DB_PASSWORD}
\else
  \echo 'ERROR: DB_PASSWORD_APP is not set'
  \quit 1
\endif

-- ============================================================
-- Roles
-- ============================================================

CREATE ROLE aflscraper_owner
  LOGIN
  PASSWORD :'AFLSCRAPER_OWNER_DB_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE;

CREATE ROLE aflscraper_app
  LOGIN
  PASSWORD :'AFLSCRAPER_APP_DB_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE;

-- Clear password variables from psql session ASAP
\unset AFLSCRAPER_OWNER_DB_PASSWORD
\unset AFLSCRAPER_APP_DB_PASSWORD

-- ============================================================
-- Database
-- ============================================================

CREATE DATABASE aflscraper_db
  OWNER aflscraper_owner
  ENCODING 'UTF8'
  TEMPLATE template0;

-- ============================================================
-- Connect to the new database
-- ============================================================

\connect aflscraper_db

-- ============================================================
-- Schema hardening
-- ============================================================

-- Remove default access
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Allow app to use schema but not create objects
GRANT USAGE ON SCHEMA public TO aflscraper_app;
REVOKE CREATE ON SCHEMA public FROM aflscraper_app;

-- Explicit database access
GRANT CONNECT ON DATABASE aflscraper_db TO aflscraper_app;

-- ============================================================
-- Default privileges (for future objects)
-- ============================================================
-- IMPORTANT: applies only to objects created by aflscraper_owner

ALTER DEFAULT PRIVILEGES FOR ROLE aflscraper_owner
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES
TO aflscraper_app;

ALTER DEFAULT PRIVILEGES FOR ROLE aflscraper_owner
GRANT USAGE, SELECT
ON SEQUENCES
TO aflscraper_app;
