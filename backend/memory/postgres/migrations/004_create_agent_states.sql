CREATE TABLE IF NOT EXISTS agent_states (
    state_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    session_id      UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    state_key       TEXT NOT NULL CHECK (length(trim(state_key)) > 0),
    state_value     JSONB NOT NULL,
    schema_version  TEXT NOT NULL DEFAULT 'agent-state-v1',
    -- Updated explicitly by repository upsert so writes remain visible in code.
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
