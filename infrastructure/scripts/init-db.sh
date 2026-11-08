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
    export POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-aihr_migration_user}"
    export POSTGRES_MIGRATION_PASSWORD="${POSTGRES_MIGRATION_PASSWORD:-local_development_migration_password_only}"
    export POSTGRES_USER="${POSTGRES_APP_USER:-${POSTGRES_USER:-aihr_app_user}}"
    export POSTGRES_PASSWORD="${POSTGRES_APP_PASSWORD:-${POSTGRES_PASSWORD:-local_development_password_only}}"
    export POSTGRES_DB="${POSTGRES_DB:-ai_hr_db}"
    export PGPASSWORD="${PGPASSWORD:-${POSTGRES_SUPERUSER_PASSWORD:-local_development_super_password_only}}"
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

    export POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-aihr_migration_user}"
    export POSTGRES_MIGRATION_PASSWORD="${POSTGRES_MIGRATION_PASSWORD}"
    export POSTGRES_USER="${POSTGRES_APP_USER:-${POSTGRES_USER:-aihr_app_user}}"
    export POSTGRES_PASSWORD="${EFFECTIVE_APP_PASSWORD}"
    export POSTGRES_DB="${POSTGRES_DB:-ai_hr_db}"
    export PGPASSWORD="${EFFECTIVE_SUPER_PASSWORD}"
fi

SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
DB_HOST="${PGHOST:-${POSTGRES_HOST:-}}"
DB_PORT="${PGPORT:-${POSTGRES_PORT:-5432}}"

echo "Starting database role initialization and credential reconciliation (env: ${APP_ENV})..."

# Determine connection method:
# 1. If explicit host is supplied (e.g. PGHOST or POSTGRES_HOST), connect via TCP.
# 2. If running inside a container with an active local socket, connect via socket.
# 3. Otherwise (e.g. CI or external host without socket), default to localhost TCP.
if [ -n "${DB_HOST}" ]; then
    psql -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
elif [ -e "/var/run/postgresql/.s.PGSQL.${DB_PORT}" ] || [ -e "/tmp/.s.PGSQL.${DB_PORT}" ]; then
    psql -v ON_ERROR_STOP=1 -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
else
    psql -v ON_ERROR_STOP=1 -h "localhost" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
fi

echo "Database roles, extensions, and privileges successfully initialized and reconciled."
