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
