CREATE TABLE IF NOT EXISTS turns (
    turn_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    token_count  INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    latency_ms   DOUBLE PRECISION CHECK (latency_ms IS NULL OR latency_ms >= 0)
);

CREATE INDEX IF NOT EXISTS idx_turns_session_id
    ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_created_at
    ON turns(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_turns_session_created_at
    ON turns(session_id, created_at DESC);
