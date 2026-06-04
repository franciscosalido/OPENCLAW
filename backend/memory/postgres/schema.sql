CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

CREATE TABLE IF NOT EXISTS agent_states (
    state_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    session_id      UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    state_key       TEXT NOT NULL CHECK (length(trim(state_key)) > 0),
    state_value     JSONB NOT NULL,
    schema_version  TEXT NOT NULL DEFAULT 'agent-state-v1',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id, session_id, state_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_states_agent_id
    ON agent_states(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_states_session_id
    ON agent_states(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_states_updated_at
    ON agent_states(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_states_agent_session
    ON agent_states(agent_id, session_id);

CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id      UUID NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
    entity_text  TEXT NOT NULL CHECK (length(trim(entity_text)) > 0),
    entity_type  TEXT NOT NULL CHECK (length(trim(entity_type)) > 0),
    start_char   INTEGER NOT NULL CHECK (start_char >= 0),
    end_char     INTEGER NOT NULL CHECK (end_char >= start_char),
    confidence   DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))
);

CREATE INDEX IF NOT EXISTS idx_entity_mentions_turn_id
    ON entity_mentions(turn_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_text
    ON entity_mentions(entity_text);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_type
    ON entity_mentions(entity_type);
