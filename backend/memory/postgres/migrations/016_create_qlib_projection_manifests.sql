CREATE TABLE IF NOT EXISTS qlib_projection_manifests (
    projection_id UUID PRIMARY KEY DEFAULT uuidv7(),
    projection_name TEXT NOT NULL CHECK (length(trim(projection_name)) > 0),
    projection_version TEXT NOT NULL CHECK (length(trim(projection_version)) > 0),
    storage_uri TEXT,
    format TEXT NOT NULL CHECK (format IN ('qlib_bin', 'parquet', 'csv', 'pandas')),
    source_query_hash TEXT NOT NULL CHECK (length(trim(source_query_hash)) > 0),
    transform_hash TEXT NOT NULL CHECK (length(trim(transform_hash)) > 0),
    checksum TEXT,
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    start_ts TIMESTAMPTZ,
    end_ts TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    source_id TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'qlib-projection-manifest-v1',
    lineage_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        start_ts IS NULL
        OR end_ts IS NULL
        OR end_ts >= start_ts
    ),
    UNIQUE(projection_name, projection_version, source_query_hash, transform_hash, format)
);

CREATE INDEX IF NOT EXISTS idx_qlib_projection_name_version
    ON qlib_projection_manifests(projection_name, projection_version);
CREATE INDEX IF NOT EXISTS idx_qlib_projection_created_at
    ON qlib_projection_manifests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qlib_projection_expires_at
    ON qlib_projection_manifests(expires_at);
CREATE INDEX IF NOT EXISTS idx_qlib_projection_format
    ON qlib_projection_manifests(format);

CREATE OR REPLACE VIEW qlib_ohlcv_v1 AS
SELECT
    i.symbol AS instrument,
    i.exchange,
    b.ts AS datetime,
    b.timeframe,
    b.open,
    b.close,
    b.high,
    b.low,
    b.volume,
    b.amount,
    COALESCE(b.factor, 1.0) AS factor,
    b.source_id,
    b.schema_version,
    b.lineage_hash
FROM market_bars b
JOIN market_instruments i ON i.instrument_id = b.instrument_id
WHERE COALESCE(
    CASE
        WHEN jsonb_typeof(b.quality_flags->'invalid') = 'boolean'
        THEN (b.quality_flags->>'invalid')::boolean
        ELSE FALSE
    END,
    FALSE
) = FALSE;
