CREATE TABLE IF NOT EXISTS audit_agent_writes (
    audit_id UUID PRIMARY KEY DEFAULT uuidv7(),
    trace_id UUID NOT NULL,
    run_id UUID REFERENCES ops_ingestion_runs (run_id),
    agent_id TEXT NOT NULL CHECK (agent_id ~ '\S'),
    repository TEXT NOT NULL CHECK (repository ~ '\S'),
    target_table TEXT NOT NULL CHECK (target_table ~ '\S'),
    -- SQLFluff RF04: "operation" is a domain column name, not a keyword alias.
    operation TEXT NOT NULL -- noqa: RF04
    CHECK (
        operation IN (
            'insert',
            'update',
            'upsert',
            'bulk_insert',
            'bulk_upsert'
        )
    ),
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    batch_hash TEXT NOT NULL CHECK (batch_hash ~ '\S'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object')
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_audit_agent_writes_trace_id -- noqa: PG01
ON audit_agent_writes (trace_id);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_audit_agent_writes_run_id -- noqa: PG01
ON audit_agent_writes (run_id)
WHERE run_id IS NOT NULL;
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_audit_agent_writes_agent_created_at -- noqa: PG01,LT05
ON audit_agent_writes (agent_id, created_at DESC);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_audit_agent_writes_repo_target_created_at -- noqa: PG01,LT05
ON audit_agent_writes (repository, target_table, created_at DESC);

-- PostgreSQL owners retain object ownership capabilities; this trigger is the
-- authoritative append-only guard in the current single-role local setup.
CREATE OR REPLACE FUNCTION prevent_audit_agent_writes_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit_agent_writes is append-only: % not permitted',
        TG_OP;
END;
$$;

CREATE OR REPLACE TRIGGER trg_audit_agent_writes_append_only
BEFORE UPDATE OR DELETE ON audit_agent_writes
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_agent_writes_mutation();

-- Defense-in-depth for future split application roles.
-- Object owners still retain owner capabilities in PostgreSQL, so the trigger
-- remains authoritative.
REVOKE UPDATE, DELETE ON audit_agent_writes FROM PUBLIC; -- noqa: CP02
