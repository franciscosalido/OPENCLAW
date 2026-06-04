CREATE TABLE IF NOT EXISTS model_runs (
    run_id UUID PRIMARY KEY DEFAULT uuidv7(),
    model_name TEXT NOT NULL CHECK (length(trim(model_name)) > 0),
    model_version TEXT NOT NULL CHECK (length(trim(model_version)) > 0),
    adapter_name TEXT NOT NULL CHECK (length(trim(adapter_name)) > 0),
    adapter_version TEXT NOT NULL CHECK (length(trim(adapter_version)) > 0),
    input_start_ts TIMESTAMPTZ NOT NULL,
    input_end_ts TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'model-run-v1',
    lineage_hash TEXT,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (input_end_ts >= input_start_ts)
);

CREATE INDEX IF NOT EXISTS idx_model_runs_model_name_created_at
    ON model_runs(model_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_runs_adapter_name_created_at
    ON model_runs(adapter_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_runs_input_window
    ON model_runs(input_start_ts, input_end_ts);
