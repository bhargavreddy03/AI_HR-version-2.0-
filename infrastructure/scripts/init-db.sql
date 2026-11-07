-- ==============================================================================
-- PostgreSQL Initial Extension & Setup Script
-- Executed on container creation by PostgreSQL entrypoint
-- ==============================================================================

-- Enable pgvector extension for neural embedding storage & cosine similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify vector extension availability
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension could not be installed';
    END IF;
END $$;
