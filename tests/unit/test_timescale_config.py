from __future__ import annotations

from pathlib import Path


SCHEMA = Path("backend/temporal/finance_schema.sql")


def _sql() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def _table_block(table: str) -> str:
    sql = _sql()
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
    return sql[start : sql.index(");", start)]


def test_timescale_hypertable_declarations_exist() -> None:
    sql = _sql()
    assert "create_hypertable('market_bars', by_range('ts')" in sql
    assert "create_hypertable('market_features', by_range('ts')" in sql
    assert "create_hypertable('kronos_forecasts', by_range('forecast_ts')" in sql


def test_hypertable_partition_columns_are_not_null() -> None:
    assert "ts TIMESTAMPTZ NOT NULL" in _table_block("market_bars")
    assert "ts TIMESTAMPTZ NOT NULL" in _table_block("market_features")
    assert "forecast_ts TIMESTAMPTZ NOT NULL" in _table_block("kronos_forecasts")


def test_hypertable_primary_keys_include_partition_column() -> None:
    assert "PRIMARY KEY (instrument_id, timeframe, ts)" in _table_block("market_bars")
    assert (
        "PRIMARY KEY (instrument_id, timeframe, ts, feature_name, feature_version)"
        in _table_block("market_features")
    )
    assert (
        "PRIMARY KEY (run_id, instrument_id, timeframe, forecast_ts, horizon_step)"
        in _table_block("kronos_forecasts")
    )
