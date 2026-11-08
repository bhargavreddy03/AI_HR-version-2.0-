-- ==============================================================================
-- PostgreSQL Initial Extension & Setup Script
-- Executed on container creation by PostgreSQL entrypoint as superuser (postgres)
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

-- 2. Create Privileged Migration / Schema Owner Role (aihr_migration_user)
-- Owns the schema and tables; executes DDL migrations. NOSUPERUSER, NOBYPASSRLS.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aihr_migration_user') THEN
        CREATE ROLE aihr_migration_user WITH LOGIN PASSWORD 'local_development_migration_password_only' CREATEDB NOSUPERUSER NOBYPASSRLS;
    ELSE
        ALTER ROLE aihr_migration_user WITH LOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;

-- 3. Create Restricted Runtime Application Role (aihr_app_user)
-- Used by FastAPI runtime & Celery workers. NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE.
-- Never owns tenant tables; strictly subject to PostgreSQL Row-Level Security (RLS).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aihr_app_user') THEN
        CREATE ROLE aihr_app_user WITH LOGIN PASSWORD 'local_development_password_only' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    ELSE
        ALTER ROLE aihr_app_user WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

-- 4. Schema Ownership & DDL Privileges
GRANT ALL ON SCHEMA public TO aihr_migration_user;
ALTER SCHEMA public OWNER TO aihr_migration_user;

GRANT USAGE ON SCHEMA public TO aihr_app_user;

-- 5. Default Privileges: Whenever aihr_migration_user creates tables/sequences/routines,
-- automatically grant restricted DML access to aihr_app_user:
ALTER DEFAULT PRIVILEGES FOR ROLE aihr_migration_user IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aihr_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE aihr_migration_user IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aihr_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE aihr_migration_user IN SCHEMA public
    GRANT EXECUTE ON ROUTINES TO aihr_app_user;

-- Also configure default privileges if tables are created by postgres (e.g. during initial setup)
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aihr_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aihr_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT EXECUTE ON ROUTINES TO aihr_app_user;

-- Grant permissions on any pre-existing tables/sequences
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aihr_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aihr_app_user;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA public TO aihr_app_user;
