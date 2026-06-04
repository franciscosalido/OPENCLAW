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
