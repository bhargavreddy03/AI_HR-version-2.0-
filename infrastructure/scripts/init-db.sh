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

# Export environment credentials with fallback to defaults
export POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-aihr_migration_user}"
export POSTGRES_MIGRATION_PASSWORD="${POSTGRES_MIGRATION_PASSWORD:-local_development_migration_password_only}"
export POSTGRES_USER="${POSTGRES_APP_USER:-${POSTGRES_USER:-aihr_app_user}}"
export POSTGRES_PASSWORD="${POSTGRES_APP_PASSWORD:-${POSTGRES_PASSWORD:-local_development_password_only}}"
export POSTGRES_DB="${POSTGRES_DB:-ai_hr_db}"

SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

if [ ! -f "${SQL_FILE}" ]; then
    echo "Error: SQL initialization file not found at ${SQL_FILE}" >&2
    exit 1
fi

echo "Starting database role initialization and credential reconciliation..."

# In container entrypoint, if PGHOST is unset or localhost is not active, connect via local socket
if [ -n "${PGHOST:-}" ]; then
    psql -v ON_ERROR_STOP=1 -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
elif [ -n "${POSTGRES_HOST:-}" ] && [ "${POSTGRES_HOST}" != "localhost" ]; then
    psql -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
else
    psql -v ON_ERROR_STOP=1 -U "${SUPERUSER}" -d "${POSTGRES_DB}" -f "${SQL_FILE}"
fi

echo "Database roles, extensions, and privileges successfully initialized and reconciled."
