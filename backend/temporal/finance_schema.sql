CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS market_instruments (
    instrument_id UUID PRIMARY KEY DEFAULT uuidv7(),
    symbol TEXT NOT NULL CHECK (length(trim(symbol)) > 0),
    exchange TEXT NOT NULL CHECK (length(trim(exchange)) > 0),
    asset_class TEXT NOT NULL CHECK (length(trim(asset_class)) > 0),
    currency TEXT,
    timezone TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, exchange)
);

CREATE INDEX IF NOT EXISTS idx_market_instruments_symbol
    ON market_instruments(symbol);
CREATE INDEX IF NOT EXISTS idx_market_instruments_exchange
    ON market_instruments(exchange);
CREATE INDEX IF NOT EXISTS idx_market_instruments_asset_class
    ON market_instruments(asset_class);
CREATE INDEX IF NOT EXISTS idx_market_instruments_created_at
    ON market_instruments(created_at DESC);

CREATE TABLE IF NOT EXISTS market_calendars (
    calendar_id UUID PRIMARY KEY DEFAULT uuidv7(),
    exchange TEXT NOT NULL CHECK (length(trim(exchange)) > 0),
    session_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    open_at TIMESTAMPTZ,
    close_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (is_open = FALSE)
        OR
        (open_at IS NOT NULL AND close_at IS NOT NULL AND close_at > open_at)
    ),
    UNIQUE(exchange, session_date)
);

CREATE INDEX IF NOT EXISTS idx_market_calendars_exchange_date
    ON market_calendars(exchange, session_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_calendars_is_open
    ON market_calendars(is_open);

CREATE TABLE IF NOT EXISTS market_bars (
    ts TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL REFERENCES market_instruments(instrument_id) ON DELETE CASCADE,
    timeframe TEXT NOT NULL CHECK (length(trim(timeframe)) > 0),

    open DOUBLE PRECISION NOT NULL CHECK (open >= 0),
    high DOUBLE PRECISION NOT NULL CHECK (high >= 0),
    low DOUBLE PRECISION NOT NULL CHECK (low >= 0),
    close DOUBLE PRECISION NOT NULL CHECK (close >= 0),
    volume DOUBLE PRECISION CHECK (volume IS NULL OR volume >= 0),
    amount DOUBLE PRECISION CHECK (amount IS NULL OR amount >= 0),
    factor DOUBLE PRECISION CHECK (factor IS NULL OR factor > 0),

    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'market-bar-v1',
    quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    lineage_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    CHECK (high >= low),
    CHECK (high >= open),
    CHECK (high >= close),
    CHECK (low <= open),
    CHECK (low <= close),

    PRIMARY KEY (instrument_id, timeframe, ts)
);

SELECT create_hypertable('market_bars', by_range('ts'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_bars_instrument_ts
    ON market_bars(instrument_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_market_bars_instrument_timeframe_ts
    ON market_bars(instrument_id, timeframe, ts DESC);
CREATE INDEX IF NOT EXISTS idx_market_bars_source_id
    ON market_bars(source_id);
CREATE INDEX IF NOT EXISTS idx_market_bars_ingested_at
    ON market_bars(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_bars_schema_version
    ON market_bars(schema_version);

CREATE TABLE IF NOT EXISTS market_features (
    ts TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL REFERENCES market_instruments(instrument_id) ON DELETE CASCADE,
    timeframe TEXT NOT NULL CHECK (length(trim(timeframe)) > 0),

    feature_name TEXT NOT NULL CHECK (length(trim(feature_name)) > 0),
    feature_value DOUBLE PRECISION,
    feature_version TEXT NOT NULL CHECK (length(trim(feature_version)) > 0),
    source_bar_version TEXT,

    source_id TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'market-feature-v1',
    lineage_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (instrument_id, timeframe, ts, feature_name, feature_version)
);

SELECT create_hypertable('market_features', by_range('ts'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_features_instrument_ts
    ON market_features(instrument_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_market_features_name_version
    ON market_features(feature_name, feature_version);
CREATE INDEX IF NOT EXISTS idx_market_features_ingested_at
    ON market_features(ingested_at DESC);

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

CREATE TABLE IF NOT EXISTS kronos_forecasts (
    forecast_ts TIMESTAMPTZ NOT NULL,
    run_id UUID NOT NULL REFERENCES model_runs(run_id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES market_instruments(instrument_id) ON DELETE CASCADE,
    timeframe TEXT NOT NULL CHECK (length(trim(timeframe)) > 0),
    horizon_step INTEGER NOT NULL CHECK (horizon_step >= 0),

    open_pred DOUBLE PRECISION,
    high_pred DOUBLE PRECISION,
    low_pred DOUBLE PRECISION,
    close_pred DOUBLE PRECISION,
    volume_pred DOUBLE PRECISION,
    amount_pred DOUBLE PRECISION,

    quantiles JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_count INTEGER CHECK (sample_count IS NULL OR sample_count >= 1),

    source_id TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version TEXT NOT NULL DEFAULT 'kronos-forecast-v1',
    lineage_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (high_pred IS NULL OR low_pred IS NULL OR high_pred >= low_pred),

    PRIMARY KEY (run_id, instrument_id, timeframe, forecast_ts, horizon_step)
);

SELECT create_hypertable('kronos_forecasts', by_range('forecast_ts'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_kronos_forecasts_instrument_ts
    ON kronos_forecasts(instrument_id, forecast_ts DESC);
CREATE INDEX IF NOT EXISTS idx_kronos_forecasts_run_id
    ON kronos_forecasts(run_id);
CREATE INDEX IF NOT EXISTS idx_kronos_forecasts_timeframe_ts
    ON kronos_forecasts(timeframe, forecast_ts DESC);
CREATE INDEX IF NOT EXISTS idx_kronos_forecasts_ingested_at
    ON kronos_forecasts(ingested_at DESC);

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
