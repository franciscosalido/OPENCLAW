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
