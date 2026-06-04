from __future__ import annotations

from pathlib import Path


SCHEMA = Path("backend/temporal/finance_schema.sql")


def _sql() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_finance_schema_contains_all_tables() -> None:
    sql = _sql()
    for table in (
        "market_instruments",
        "market_calendars",
        "market_bars",
        "market_features",
        "model_runs",
        "kronos_forecasts",
        "qlib_projection_manifests",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_entity_primary_keys_use_uuidv7() -> None:
    sql = _sql()
    for table in (
        "market_instruments",
        "market_calendars",
        "model_runs",
        "qlib_projection_manifests",
    ):
        start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
        block = sql[start : sql.index(");", start)]
        assert "PRIMARY KEY DEFAULT uuidv7()" in block


def test_hypertables_use_create_hypertable_by_range() -> None:
    sql = _sql()
    assert "create_hypertable('market_bars', by_range('ts'), if_not_exists => TRUE)" in sql
    assert "create_hypertable('market_features', by_range('ts'), if_not_exists => TRUE)" in sql
    assert (
        "create_hypertable('kronos_forecasts', by_range('forecast_ts'), "
        "if_not_exists => TRUE)"
    ) in sql


def test_schema_uses_temporal_and_jsonb_types() -> None:
    sql = _sql()
    assert sql.count("TIMESTAMPTZ") >= 15
    for column in ("metadata JSONB", "params JSONB", "metrics JSONB", "quantiles JSONB", "quality_flags JSONB"):
        assert column in sql


def test_schema_contains_finance_constraints() -> None:
    sql = _sql()
    assert "CHECK (high >= low)" in sql
    assert "CHECK (high >= open)" in sql
    assert "CHECK (low <= close)" in sql
    assert "CHECK (format IN ('qlib_bin', 'parquet', 'csv', 'pandas'))" in sql
    assert "row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0)" in sql
    assert "UNIQUE(symbol, exchange)" in sql
    assert "UNIQUE(exchange, session_date)" in sql


def test_schema_has_no_generic_eav_store() -> None:
    sql = _sql().lower()
    assert "create table if not exists temporal_events" not in sql
    assert "create table if not exists key_values" not in sql
    for table in ("market_bars", "kronos_forecasts"):
        block = sql[sql.index(f"create table if not exists {table}") :]
        block = block[: block.index(");")]
        assert "\n    key " not in block
        assert "\n    value " not in block


def test_qlib_ohlcv_view_is_not_materialized() -> None:
    sql = _sql()
    assert "CREATE OR REPLACE VIEW qlib_ohlcv_v1" in sql
    assert "CREATE MATERIALIZED VIEW qlib_ohlcv_v1" not in sql


def test_qlib_ohlcv_view_defaults_factor_and_excludes_invalid_bars() -> None:
    sql = _sql()
    start = sql.index("CREATE OR REPLACE VIEW qlib_ohlcv_v1")
    view_sql = sql[start:]

    assert "COALESCE(b.factor, 1.0) AS factor" in view_sql
    assert "jsonb_typeof(b.quality_flags->'invalid') = 'boolean'" in view_sql
    assert "THEN (b.quality_flags->>'invalid')::boolean" in view_sql
    assert ") = FALSE" in view_sql
