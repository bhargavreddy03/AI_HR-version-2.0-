#!/usr/bin/env bash
# ==============================================================================
# Database Bootstrap and Role Reconciliation Script
# Safely initializes PostgreSQL roles, extensions, and privileges
# using configured environment credentials without leaking secrets to CLI or logs.
# ==============================================================================
set -eo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/init-db.sql"
if [ ! -f "${SQL_FILE}" ] && [ -f "/infrastructure/scripts/init-db.sql" ]; then
    SQL_FILE="/infrastructure/scripts/init-db.sql"
fi

if [ ! -f "${SQL_FILE}" ]; then
    echo "Error: SQL initialization file not found at ${SQL_FILE}" >&2
    exit 1
fi

APP_ENV="${ENVIRONMENT:-${APP_ENV:-production}}"

# In development mode, provide convenient local defaults if not already set.
# Outside development (e.g. production, staging, testing), explicit credentials are strictly required.
if [ "${APP_ENV}" = "development" ] || [ "${APP_ENV}" = "dev" ] || [ "${APP_ENV}" = "local" ]; then
    export POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
    export POSTGRES_SUPERUSER_PASSWORD="${POSTGRES_SUPERUSER_PASSWORD:-${PGPASSWORD:-local_development_super_password_only}}"
    export PGPASSWORD="${POSTGRES_SUPERUSER_PASSWORD}"
    export POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-aihr_migration_user}"
    export POSTGRES_MIGRATION_PASSWORD="${POSTGRES_MIGRATION_PASSWORD:-local_development_migration_password_only}"
    export POSTGRES_APP_USER="${POSTGRES_APP_USER:-aihr_app_user}"
    export POSTGRES_USER="${POSTGRES_APP_USER}"
    export POSTGRES_APP_PASSWORD="${POSTGRES_APP_PASSWORD:-${POSTGRES_PASSWORD:-local_development_password_only}}"
    export POSTGRES_DB="${POSTGRES_DB:-ai_hr_db}"
else
    # Outside development: fail immediately if required secrets are missing
    if [ -z "${POSTGRES_MIGRATION_PASSWORD}" ]; then
        echo "Error: POSTGRES_MIGRATION_PASSWORD must be explicitly configured outside development (env: ${APP_ENV})." >&2
        exit 1
    fi

    EFFECTIVE_APP_PASSWORD="${POSTGRES_APP_PASSWORD:-${POSTGRES_PASSWORD:-}}"
    if [ -z "${EFFECTIVE_APP_PASSWORD}" ]; then
        echo "Error: POSTGRES_APP_PASSWORD or POSTGRES_PASSWORD must be explicitly configured outside development (env: ${APP_ENV})." >&2
        exit 1
    fi

    EFFECTIVE_SUPER_PASSWORD="${PGPASSWORD:-${POSTGRES_SUPERUSER_PASSWORD:-}}"
    if [ -z "${EFFECTIVE_SUPER_PASSWORD}" ]; then
        echo "Error: PGPASSWORD or POSTGRES_SUPERUSER_PASSWORD must be explicitly configured outside development (env: ${APP_ENV})." >&2
        exit 1
    fi

    export POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
    export POSTGRES_SUPERUSER_PASSWORD="${EFFECTIVE_SUPER_PASSWORD}"
    export PGPASSWORD="${EFFECTIVE_SUPER_PASSWORD}"
    export POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-aihr_migration_user}"
    export POSTGRES_MIGRATION_PASSWORD="${POSTGRES_MIGRATION_PASSWORD}"
    export POSTGRES_APP_USER="${POSTGRES_APP_USER:-aihr_app_user}"
    export POSTGRES_USER="${POSTGRES_APP_USER}"
    export POSTGRES_APP_PASSWORD="${EFFECTIVE_APP_PASSWORD}"
    export POSTGRES_DB="${POSTGRES_DB:-ai_hr_db}"
fi

SUPERUSER="${POSTGRES_SUPERUSER}"
DB_HOST="${PGHOST:-${POSTGRES_HOST:-}}"
DB_PORT="${PGPORT:-${POSTGRES_PORT:-5432}}"

# Validate role distinctness (never allow role collisions between superuser, migration, and app roles)
if [ "${POSTGRES_SUPERUSER}" = "${POSTGRES_MIGRATION_USER}" ] || \
   [ "${POSTGRES_SUPERUSER}" = "${POSTGRES_APP_USER}" ] || \
   [ "${POSTGRES_MIGRATION_USER}" = "${POSTGRES_APP_USER}" ]; then
    echo "Error: Role collision detected. Bootstrap superuser (${POSTGRES_SUPERUSER}), migration role (${POSTGRES_MIGRATION_USER}), and runtime application role (${POSTGRES_APP_USER}) must all be distinct." >&2
    exit 1
fi

echo "Starting database role initialization and credential reconciliation (env: ${APP_ENV})..."

# Detect execution context:
# When executing inside the official PostgreSQL Docker entrypoint initialization,
# the temporary postmaster listens on a local Unix socket (with listen_addresses='').
# Do NOT connect via TCP to container service hostnames (e.g. POSTGRES_HOST=postgres).
IS_DOCKER_ENTRYPOINT=false
if [[ "${BASH_SOURCE[0]}" == *"/docker-entrypoint-initdb.d/"* ]] || [ -n "${PGDATA:-}" -a -d "/docker-entrypoint-initdb.d" ]; then
    IS_DOCKER_ENTRYPOINT=true
fi

if [ "${IS_DOCKER_ENTRYPOINT}" = "true" ]; then
    echo "Executing inside PostgreSQL Docker entrypoint; connecting via local Unix domain socket..."
    SOCKET_DIR=""
    if [ -S "/var/run/postgresql/.s.PGSQL.${DB_PORT}" ]; then
        SOCKET_DIR="/var/run/postgresql"
    elif [ -S "/tmp/.s.PGSQL.${DB_PORT}" ]; then
        SOCKET_DIR="/tmp"
    fi

    if [ -n "${SOCKET_DIR}" ]; then
        psql -v ON_ERROR_STOP=1 -h "${SOCKET_DIR}" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
    else
        psql -v ON_ERROR_STOP=1 -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
    fi
else
    # External execution (host machine or CI runner against an already-running PostgreSQL server)
    if [ -n "${DB_HOST}" ]; then
        psql -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
    elif [ -S "/var/run/postgresql/.s.PGSQL.${DB_PORT}" ] || [ -S "/tmp/.s.PGSQL.${DB_PORT}" ]; then
        psql -v ON_ERROR_STOP=1 -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
    else
        psql -v ON_ERROR_STOP=1 -h "localhost" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
    fi
fi

echo "Database roles, extensions, and privileges successfully initialized and reconciled."
