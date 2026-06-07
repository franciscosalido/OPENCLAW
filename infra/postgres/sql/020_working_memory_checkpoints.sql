CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS working_memory_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT uuidv7(),
    agent_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    snapshot_epoch BIGINT NOT NULL,
    collection_name TEXT NOT NULL,
    vector_name TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    vector_dim INTEGER NOT NULL CHECK (vector_dim > 0),
    snapshot_kind TEXT NOT NULL CHECK (snapshot_kind IN ('full','delta')),
    point_count INTEGER NOT NULL CHECK (point_count >= 0),
    checksum TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT 'working-memory-snapshot-v1',
    UNIQUE(agent_id, session_id, snapshot_epoch)
);

CREATE TABLE IF NOT EXISTS working_memory_snapshot_points (
    snapshot_id UUID NOT NULL REFERENCES working_memory_snapshots(snapshot_id) ON DELETE CASCADE,
    point_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    memory_kind TEXT NOT NULL,
    source_ref TEXT,
    topic TEXT,
    safe_summary TEXT CHECK (safe_summary IS NULL OR length(safe_summary) <= 512),
    embedding_model TEXT NOT NULL,
    vector_dim INTEGER NOT NULL CHECK (vector_dim > 0),
    memory_vector vector(768),
    importance DOUBLE PRECISION CHECK (importance IS NULL OR (importance >= 0 AND importance <= 1)),
    recency_ts TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    payload_checksum TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'working-memory-snapshot-point-v1',
    PRIMARY KEY (snapshot_id, point_id)
);

CREATE INDEX IF NOT EXISTS idx_wm_snapshots_agent_session_created_at
    ON working_memory_snapshots(agent_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wm_snapshots_session_epoch
    ON working_memory_snapshots(session_id, snapshot_epoch DESC);

CREATE INDEX IF NOT EXISTS idx_wm_snapshot_points_agent_session
    ON working_memory_snapshot_points(agent_id, session_id);

CREATE INDEX IF NOT EXISTS idx_wm_snapshot_points_memory_kind
    ON working_memory_snapshot_points(memory_kind);

CREATE INDEX IF NOT EXISTS idx_wm_snapshot_points_expires_at
    ON working_memory_snapshot_points(expires_at);

CREATE INDEX IF NOT EXISTS idx_wm_snapshot_points_payload_checksum
    ON working_memory_snapshot_points(payload_checksum);
