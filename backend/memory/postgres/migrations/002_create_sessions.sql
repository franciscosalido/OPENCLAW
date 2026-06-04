CREATE TABLE IF NOT EXISTS sessions (
    session_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    user_id      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_sessions_agent_id
    ON sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at
    ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_agent_created_at
    ON sessions(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id
    ON sessions(user_id)
    WHERE user_id IS NOT NULL;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sessions_updated_at ON sessions;
CREATE TRIGGER trg_sessions_updated_at
BEFORE UPDATE ON sessions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
