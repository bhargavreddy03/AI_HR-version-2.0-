#!/usr/bin/env bash
# ==============================================================================
# AI HR Intelligence Platform - Backend & Celery Worker Entrypoint
# ==============================================================================
# 1. Runs Alembic migrations when starting the web server (uvicorn).
# 2. Retries database connection during container startup handshake.
# 3. Never swallows migration errors: fails fast if migrations cannot be applied.
# 4. Transparently hands off execution to Celery worker, Uvicorn, or custom commands.
# ==============================================================================
set -eo pipefail

# Execute database migrations on web server startup if enabled
if [ "${RUN_MIGRATIONS:-true}" = "true" ] && [ "$1" = "uvicorn" ]; then
    echo "=================================================================="
    echo "AI HR Platform: Checking database connectivity & running migrations..."
    echo "=================================================================="
    
    MAX_RETRIES=30
    RETRY_COUNT=0
    MIGRATED=false

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if alembic upgrade head; then
            echo "Alembic migrations applied successfully."
            MIGRATED=true
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo "Database connection or migration not ready yet. Retrying in 2s... (${RETRY_COUNT}/${MAX_RETRIES})"
            sleep 2
        fi
    done

    if [ "$MIGRATED" != "true" ]; then
        echo "ERROR: Database migration execution failed after ${MAX_RETRIES} attempts. Aborting startup." >&2
        exit 1
    fi
fi

exec "$@"
