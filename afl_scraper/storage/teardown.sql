-- =========================
-- Terminate active connections
-- =========================

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'aflscraper_db'
  AND pid <> pg_backend_pid();

-- =========================
-- Drop database
-- =========================

DROP DATABASE IF EXISTS aflscraper_db;

-- =========================
-- Drop roles
-- =========================

DROP ROLE IF EXISTS aflscraper_app;
DROP ROLE IF EXISTS aflscraper_owner;
