-- SECTION A: Read-only views

CREATE OR REPLACE VIEW macro_observations_latest_revision AS
SELECT DISTINCT ON (series_code, ref_ts)
    series_code,
    ref_ts,
    revision,
    value,
    source_id,
    run_id,
    lineage_hash,
    schema_version,
    quality_flags,
    metadata,
    ingested_at
FROM macro_observations
ORDER BY series_code ASC, ref_ts ASC, revision DESC;

CREATE OR REPLACE VIEW treasury_latest_prices_view AS
SELECT DISTINCT ON (bond_id)
    bond_id,
    ts,
    price_bid,
    price_ask,
    rate_bid,
    rate_ask,
    base_value,
    source_id,
    run_id,
    lineage_hash,
    schema_version,
    quality_flags,
    metadata,
    ingested_at
FROM treasury_prices
ORDER BY bond_id ASC, ts DESC;

CREATE OR REPLACE VIEW fund_daily_info_latest_revision AS
SELECT DISTINCT ON (fund_cnpj, ts)
    fund_cnpj,
    ts,
    revision,
    total_portfolio_value,
    quota_value,
    net_worth,
    inflow,
    outflow,
    shareholders,
    source_id,
    run_id,
    lineage_hash,
    schema_version,
    quality_flags,
    metadata,
    ingested_at
FROM fund_daily_info
ORDER BY fund_cnpj ASC, ts ASC, revision DESC;

CREATE OR REPLACE VIEW fund_monthly_quota_returns AS
WITH ranked AS (
    SELECT
        fund_cnpj,
        ts,
        quota_value,
        date_trunc('month', ts) AS month_ts,
        row_number() OVER (
            PARTITION BY fund_cnpj, date_trunc('month', ts)
            ORDER BY ts ASC
        ) AS first_rank,
        row_number() OVER (
            PARTITION BY fund_cnpj, date_trunc('month', ts)
            ORDER BY ts DESC
        ) AS last_rank
    FROM fund_daily_info_latest_revision
),

monthly AS (
    SELECT
        fund_cnpj,
        month_ts,
        max(quota_value) FILTER (WHERE first_rank = 1) AS first_quota,
        max(quota_value) FILTER (WHERE last_rank = 1) AS last_quota
    FROM ranked
    GROUP BY fund_cnpj, month_ts
)

SELECT
    fund_cnpj,
    month_ts,
    first_quota,
    last_quota,
    (last_quota / nullif(first_quota, 0)) - 1 AS monthly_return
FROM monthly;

-- SECTION B: Continuous aggregates where semantics are true aggregation

CREATE MATERIALIZED VIEW IF NOT EXISTS market_bars_1d_cagg
WITH (timescaledb.continuous) AS
SELECT
    instrument_id,
    timeframe,
    'market-bar-1d-v1'::TEXT AS schema_version,
    time_bucket(INTERVAL '1 day', ts) AS ts,
    first(open, ts) AS open,
    max(high) AS high,
    min(low) AS low,
    last("close", ts) AS "close", -- noqa: RF04,RF06,LT05
    sum(volume) AS volume,
    sum(amount) AS amount,
    min(source_id) AS source_id,
    max(ingested_at) AS ingested_at
FROM market_bars
GROUP BY instrument_id, timeframe, time_bucket(INTERVAL '1 day', ts)
WITH NO DATA;

CREATE OR REPLACE VIEW market_bars_1d AS
SELECT
    instrument_id,
    timeframe,
    ts,
    open,
    high,
    low,
    close,
    volume,
    amount,
    source_id,
    ingested_at,
    schema_version
FROM market_bars_1d_cagg;

CREATE OR REPLACE VIEW vw_kronos_ohlcva_input AS
SELECT
    instrument_id,
    ts,
    open,
    high,
    low,
    close,
    volume,
    amount,
    timeframe,
    schema_version
FROM market_bars_1d;

-- SECTION C: Refresh policies for CAGGs where safe
-- Intentionally no automatic refresh policy in V1. The migration runner is
-- transactional, and this closeout PR must not schedule heavy backfills.

-- SECTION D: Compression readiness/conservative compression
ALTER MATERIALIZED VIEW market_bars_1d_cagg
SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_id,timeframe',
    timescaledb.compress_orderby = 'ts DESC'
);

-- Compression policy is intentionally deferred in V1. Operators may add a
-- conservative policy after observing volume and refresh behavior.

-- SECTION E: RETENTION POLICIES — INTENTIONALLY ABSENT IN V1
-- FINLIB-0 does not install any destructive time-series retention job.
