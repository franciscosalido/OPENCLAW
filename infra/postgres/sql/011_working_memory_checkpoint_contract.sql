-- PR-09 contract: pgvector is the durable checkpoint for future fast working memory.
-- This table is not the hot working memory backend and is not on the critical path.

CREATE TABLE IF NOT EXISTS working_memory_checkpoints (
    checkpoint_id UUID PRIMARY KEY DEFAULT uuidv7(),
    agent_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    topic TEXT,
    embedding_model TEXT NOT NULL,
    vector_dim INTEGER NOT NULL CHECK (vector_dim > 0),
    memory_vector vector,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    checksum TEXT NOT NULL,
    ttl_seconds INTEGER CHECK (ttl_seconds IS NULL OR ttl_seconds > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    schema_version TEXT NOT NULL DEFAULT 'working-memory-checkpoint-v1',
    UNIQUE(agent_id, session_id, topic, embedding_model, checksum)
);

CREATE INDEX IF NOT EXISTS idx_working_memory_agent_session_created_at
    ON working_memory_checkpoints(agent_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_working_memory_expires_at
    ON working_memory_checkpoints(expires_at);

CREATE INDEX IF NOT EXISTS idx_working_memory_embedding_model
    ON working_memory_checkpoints(embedding_model);

CREATE INDEX IF NOT EXISTS idx_working_memory_metadata_gin
    ON working_memory_checkpoints USING GIN(metadata);
