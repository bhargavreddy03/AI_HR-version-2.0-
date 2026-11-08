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
DB_HOST="${PGHOST:-${POSTGRES_HOST:-}}"
DB_PORT="${PGPORT:-${POSTGRES_PORT:-5432}}"

if [ ! -f "${SQL_FILE}" ]; then
    echo "Error: SQL initialization file not found at ${SQL_FILE}" >&2
    exit 1
fi

echo "Starting database role initialization and credential reconciliation..."

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
