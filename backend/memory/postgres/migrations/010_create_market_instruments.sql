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
