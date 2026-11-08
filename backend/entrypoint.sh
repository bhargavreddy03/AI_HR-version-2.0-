#!/usr/bin/env bash
# ==============================================================================
# AI HR Intelligence Platform - Backend & Celery Worker Entrypoint
# ==============================================================================
# 1. Runs Alembic migrations when starting the web server (uvicorn).
# 2. Never swallows migration errors: fails fast if migrations cannot be applied.
# 3. Transparently hands off execution to Celery worker, Uvicorn, or custom commands.
# ==============================================================================
set -eo pipefail

# Execute database migrations on web server startup if enabled
if [ "${RUN_MIGRATIONS:-true}" = "true" ] && [ "$1" = "uvicorn" ]; then
    echo "=================================================================="
    echo "AI HR Platform: Checking & applying database migrations..."
    echo "=================================================================="
    if alembic upgrade head; then
        echo "Alembic migrations applied successfully."
    else
        echo "ERROR: Database migration execution failed. Aborting startup." >&2
        exit 1
    fi
fi

exec "$@"
