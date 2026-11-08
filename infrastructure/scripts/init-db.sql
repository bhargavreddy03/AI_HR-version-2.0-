-- ==============================================================================
-- PostgreSQL Initial Extension & Role Setup Script
-- Executed on container creation by PostgreSQL entrypoint as superuser (postgres)
-- Consumes credentials securely from environment variables without hardcoded passwords.
-- ==============================================================================

-- 1. Enable pgvector extension for neural embedding storage & cosine similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify vector extension availability
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension could not be installed';
    END IF;
END $$;

-- 2. Read configured migration and application credentials via psql \getenv
-- Environment variables are read directly without appearing in process listings or logs.

\getenv mig_user POSTGRES_MIGRATION_USER
\if :{?mig_user}
\else
  \set mig_user 'aihr_migration_user'
\endif

\getenv mig_password POSTGRES_MIGRATION_PASSWORD
\if :{?mig_password}
\else
  \echo 'FATAL: POSTGRES_MIGRATION_PASSWORD environment variable is required'
  \q 1
\endif

\getenv app_user POSTGRES_APP_USER
\if :{?app_user}
\else
  \getenv app_user POSTGRES_USER
  \if :{?app_user}
  \else
    \set app_user 'aihr_app_user'
  \endif
\endif

\getenv app_password POSTGRES_APP_PASSWORD
\if :{?app_password}
\else
  \getenv app_password POSTGRES_PASSWORD
  \if :{?app_password}
  \else
    \echo 'FATAL: POSTGRES_APP_PASSWORD or POSTGRES_PASSWORD environment variable is required'
    \q 1
  \endif
\endif

-- Ensure app_user is not inadvertently set to the bootstrap superuser name
SELECT (CASE WHEN :'app_user' = 'postgres' OR :'app_user' = '' THEN 'aihr_app_user' ELSE :'app_user' END) AS effective_app_user \gset
SELECT (CASE WHEN :'mig_user' = '' THEN 'aihr_migration_user' ELSE :'mig_user' END) AS effective_mig_user \gset

-- 3. Create or Reconcile Migration / Schema Owner Role
-- Owns the schema and tables; executes DDL migrations.
-- Explicitly restricted: NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE.
SELECT count(*) AS role_exists FROM pg_roles WHERE rolname = :'effective_mig_user' \gset mig_
\if :mig_role_exists
    ALTER ROLE :"effective_mig_user" WITH LOGIN PASSWORD :'mig_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\else
    CREATE ROLE :"effective_mig_user" WITH LOGIN PASSWORD :'mig_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\endif

-- 4. Create or Reconcile Restricted Runtime Application Role
-- Used by FastAPI runtime & Celery workers.
-- Explicitly restricted: NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE.
-- Never owns tenant tables; strictly subject to PostgreSQL Row-Level Security (RLS).
SELECT count(*) AS role_exists FROM pg_roles WHERE rolname = :'effective_app_user' \gset app_
\if :app_role_exists
    ALTER ROLE :"effective_app_user" WITH LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\else
    CREATE ROLE :"effective_app_user" WITH LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\endif

-- 5. Schema Ownership & DDL Privileges
GRANT ALL ON SCHEMA public TO :"effective_mig_user";
ALTER SCHEMA public OWNER TO :"effective_mig_user";

GRANT USAGE ON SCHEMA public TO :"effective_app_user";

-- 6. Default Privileges: Whenever effective_mig_user creates tables/sequences/routines,
-- automatically grant restricted DML access to effective_app_user:
ALTER DEFAULT PRIVILEGES FOR ROLE :"effective_mig_user" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"effective_app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"effective_mig_user" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"effective_app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"effective_mig_user" IN SCHEMA public
    GRANT EXECUTE ON ROUTINES TO :"effective_app_user";

-- Also configure default privileges if tables are created by postgres (bootstrap role)
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"effective_app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"effective_app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT EXECUTE ON ROUTINES TO :"effective_app_user";

-- Grant permissions on any pre-existing tables/sequences in public schema
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"effective_app_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"effective_app_user";
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA public TO :"effective_app_user";
