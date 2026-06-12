CREATE TABLE IF NOT EXISTS ops_ingestion_watermarks (
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    dataset TEXT NOT NULL CHECK (dataset ~ '\S'),
    -- Textual label for observability only; watermark_ts is the monotonic key.
    watermark_value TEXT NOT NULL CHECK (watermark_value ~ '\S'),
    watermark_ts TIMESTAMPTZ,
    source_snapshot_hash TEXT CHECK (
        source_snapshot_hash IS NULL OR source_snapshot_hash ~ '\S'
    ),
    run_id UUID REFERENCES ops_ingestion_runs (run_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    PRIMARY KEY (source_id, dataset)
);

-- PostgreSQL supports CREATE OR REPLACE for trigger functions/triggers; this
-- keeps the migration idempotent while preserving transactional execution.
CREATE OR REPLACE FUNCTION prevent_ops_watermark_regression()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.watermark_ts IS NOT NULL AND NEW.watermark_ts IS NULL THEN
        RAISE EXCEPTION 'watermark_ts cannot regress to null';
    END IF;

    IF
        OLD.watermark_ts IS NOT NULL
        AND NEW.watermark_ts IS NOT NULL
        AND NEW.watermark_ts < OLD.watermark_ts
    THEN
        RAISE EXCEPTION 'watermark_ts cannot regress';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_ops_watermark_no_regression
BEFORE UPDATE OF watermark_ts ON ops_ingestion_watermarks
FOR EACH ROW
EXECUTE FUNCTION prevent_ops_watermark_regression();

CREATE TABLE IF NOT EXISTS ops_data_quality_checks (
    check_id UUID PRIMARY KEY DEFAULT uuidv7(),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    check_name TEXT NOT NULL CHECK (check_name ~ '\S'),
    target_table TEXT NOT NULL CHECK (target_table ~ '\S'),
    severity TEXT NOT NULL
    CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    passed BOOLEAN NOT NULL,
    observed JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(observed) = 'object'),
    expected JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(expected) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object')
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_data_quality_checks_run_id -- noqa: PG01
ON ops_data_quality_checks (run_id);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_data_quality_checks_severity_passed -- noqa: PG01,LT05
ON ops_data_quality_checks (severity, passed);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_data_quality_checks_created_at -- noqa: PG01
ON ops_data_quality_checks (created_at DESC);

CREATE TABLE IF NOT EXISTS ops_outbox_events (
    event_id UUID PRIMARY KEY DEFAULT uuidv7(),
    event_type TEXT NOT NULL CHECK (event_type ~ '\S'),
    aggregate_type TEXT NOT NULL CHECK (aggregate_type ~ '\S'),
    aggregate_id TEXT NOT NULL CHECK (aggregate_id ~ '\S'),
    payload JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(payload) = 'object'),
    status TEXT NOT NULL DEFAULT 'pending'
    CHECK (
        status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')
    ),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_by TEXT CHECK (locked_by IS NULL OR locked_by ~ '\S'),
    locked_at TIMESTAMPTZ,
    trace_id UUID,
    run_id UUID REFERENCES ops_ingestion_runs (run_id),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (attempts <= max_attempts),
    CHECK (
        status <> 'processing'
        OR (locked_by IS NOT NULL AND locked_at IS NOT NULL)
    )
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_outbox_pending -- noqa: PG01
ON ops_outbox_events (next_attempt_at, created_at)
WHERE status = 'pending';
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_outbox_events_run_id -- noqa: PG01
ON ops_outbox_events (run_id);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_ops_outbox_events_status_created_at -- noqa: PG01,LT05
ON ops_outbox_events (status, created_at DESC);

-- Official FINLIB-0 outbox poll contract:
-- SELECT *
-- FROM ops_outbox_events
-- WHERE status = 'pending'
--   AND next_attempt_at <= now()
-- ORDER BY created_at
-- FOR UPDATE SKIP LOCKED
-- LIMIT $1;
