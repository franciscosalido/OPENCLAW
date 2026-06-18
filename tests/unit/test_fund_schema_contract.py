from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any


MIGRATION = Path(
    "backend/memory/postgres/migrations/024_create_fund_registry_daily_info.sql"
)
SDD = Path("docs/specs/finlib-0/pr-07-fund-library.md")
CSV_SAMPLE = """CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
12.345.678/0001-90;2026-06-11;1500000000.00;15.432100;1498000000.00;50000.00;25000.00;12500
"""
LINEAGE_FIELDS = (
    "fund_cnpj",
    "ts",
    "total_portfolio_value",
    "quota_value",
    "net_worth",
    "inflow",
    "outflow",
    "shareholders",
    "source_id",
    "schema_version",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def _normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", value)


def _timestamp(value: str) -> str:
    ref_ts = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return ref_ts.isoformat()


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _lineage_hash(row: dict[str, Any]) -> str:
    payload = {field: str(row[field]) for field in LINEAGE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sample_row() -> dict[str, Any]:
    parsed = next(csv.DictReader(StringIO(CSV_SAMPLE), delimiter=";"))
    row: dict[str, Any] = {
        "fund_cnpj": _normalize_cnpj(parsed["CNPJ_FUNDO"]),
        "ts": _timestamp(parsed["DT_COMPTC"]),
        "total_portfolio_value": _decimal(parsed["VL_TOTAL"]),
        "quota_value": _decimal(parsed["VL_QUOTA"]),
        "net_worth": _decimal(parsed["VL_PATRIM_LIQ"]),
        "inflow": _decimal(parsed["CAPTC_DIA"]),
        "outflow": _decimal(parsed["RESG_DIA"]),
        "shareholders": int(parsed["NR_COTST"]),
        "source_id": "cvm_informes_diarios",
        "schema_version": 1,
    }
    row["lineage_hash"] = _lineage_hash(row)
    return row


def test_migration_024_exists_and_is_non_destructive() -> None:
    sql = _sql().lower()

    assert MIGRATION.exists()
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "alter table" not in sql
    assert "fund." not in sql
    assert "market." not in sql
    assert "ops." not in sql
    assert "audit." not in sql


def test_migration_scope_is_limited_to_fund_objects() -> None:
    lower_sql = _sql().lower()

    assert lower_sql.count("create table if not exists") == 2
    assert "create table if not exists fund_registry" in lower_sql
    assert "create table if not exists fund_daily_info" in lower_sql

    for forbidden in (
        "treasury_",
        "macro_series_catalog",
        "macro_observations",
        "fi_instruments",
        "debenture",
        "fundamentals_",
        "repository",
        "agent",
        "qdrant",
        "vector",
        "pydanticai",
        "langgraph",
        "crewai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
    ):
        assert forbidden not in lower_sql


def test_fund_registry_contract() -> None:
    compact = _compact_sql()

    assert "fund_cnpj TEXT PRIMARY KEY CHECK (fund_cnpj ~ '^[0-9]{14}$')" in compact
    assert "legal_name TEXT NOT NULL CHECK (legal_name ~ '\\S')" in compact
    assert "cvm_class TEXT CHECK (cvm_class IS NULL OR cvm_class ~ '\\S')" in compact
    assert "fund_type TEXT CHECK (fund_type IS NULL OR fund_type ~ '\\S')" in compact
    assert "status TEXT NOT NULL DEFAULT 'unknown'" in compact
    assert "status IN ('active', 'cancelled', 'inactive', 'unknown')" in compact
    assert "registered_at DATE" in compact
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in compact
    assert "CHECK (jsonb_typeof(metadata) = 'object')" in compact
    assert "CNPJ_FUNDO" not in compact
    assert "12.345.678/0001-90" not in compact


def test_fund_daily_info_revisioned_hypertable_contract() -> None:
    compact = _compact_sql()

    assert "fund_cnpj TEXT NOT NULL REFERENCES fund_registry (fund_cnpj)" in compact
    assert "ts TIMESTAMPTZ NOT NULL" in compact
    assert "ts DATE" not in compact
    assert "revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)" in compact
    assert "PRIMARY KEY (fund_cnpj, ts, revision)" in compact
    assert "PRIMARY KEY (fund_cnpj, ts)" not in compact
    assert "UNIQUE (lineage_hash, ts)" in compact
    assert "UNIQUE (lineage_hash)" not in compact
    assert "SELECT create_hypertable(" in compact
    assert "'fund_daily_info'" in compact
    assert "'ts'" in compact
    assert "chunk_time_interval => INTERVAL '1 month'" in compact
    assert "if_not_exists => TRUE" in compact
    assert compact.count("SELECT create_hypertable(") == 1
    assert "'fund_registry'" not in compact.split("SELECT create_hypertable(", 1)[1]


def test_fund_daily_info_quality_and_provenance_contract() -> None:
    compact = _compact_sql()

    assert "quota_value NUMERIC NOT NULL CHECK (quota_value > 0)" in compact
    assert "net_worth NUMERIC NOT NULL" in compact
    assert "net_worth NUMERIC NOT NULL CHECK" not in compact
    assert "shareholders INTEGER NOT NULL CHECK (shareholders >= 0)" in compact
    assert "inflow NUMERIC CHECK (inflow IS NULL OR inflow >= 0)" in compact
    assert "outflow NUMERIC CHECK (outflow IS NULL OR outflow >= 0)" in compact
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id)" in compact
    assert "lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\\S')" in compact
    assert (
        "schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0)"
        in compact
    )
    assert "CHECK (jsonb_typeof(quality_flags) = 'object')" in compact
    assert compact.count("CHECK (jsonb_typeof(metadata) = 'object')") == 2


def test_text_constraints_use_regex_not_btrim() -> None:
    compact = _compact_sql()

    assert "btrim(" not in compact.lower()
    assert "~ '\\S'" in compact


def test_migration_seeds_cvm_source() -> None:
    compact = _compact_sql()

    assert "INSERT INTO ops_data_sources" in compact
    assert "'cvm_informes_diarios'" in compact
    assert "'regulator'" in compact
    assert "CSV compactado" in _sql()
    assert "reapresentacoes" in _sql()
    assert "ON CONFLICT (source_id) DO UPDATE SET" in compact


def test_sdd_documents_csv_revision_lineage_and_audit_contract() -> None:
    sdd = SDD.read_text(encoding="utf-8")

    assert "CSV" in sdd
    assert "DT_COMPTC" in sdd
    assert "YYYY-MM-DD 00:00:00+00" in sdd
    assert "fund_cnpj" in sdd
    assert "`ts`" in sdd
    assert "revision = max(revision) + 1" in sdd
    assert "advisory lock keyed" in sdd
    assert "`(fund_cnpj, ts)`" in sdd
    assert "audit_agent_writes" in sdd
    assert "exactly one" in sdd
    assert "No data agent may issue `DELETE`" in sdd


def test_csv_sample_round_trips_to_normalized_row() -> None:
    row = _sample_row()

    assert row["fund_cnpj"] == "12345678000190"
    assert row["ts"] == "2026-06-11T00:00:00+00:00"
    assert row["total_portfolio_value"] == Decimal("1500000000.00")
    assert row["quota_value"] == Decimal("15.432100")
    assert row["net_worth"] == Decimal("1498000000.00")
    assert row["inflow"] == Decimal("50000.00")
    assert row["outflow"] == Decimal("25000.00")
    assert row["shareholders"] == 12500
    assert len(str(row["lineage_hash"])) == 64
    assert all(char in "0123456789abcdef" for char in str(row["lineage_hash"]))


def test_lineage_hash_changes_with_core_identity_and_economic_fields() -> None:
    row = _sample_row()

    for field, value in (
        ("fund_cnpj", "99999999000199"),
        ("ts", "2026-06-12T00:00:00+00:00"),
        ("quota_value", Decimal("15.500000")),
        ("net_worth", Decimal("1499000000.00")),
    ):
        changed = dict(row)
        changed[field] = value
        assert _lineage_hash(row) != _lineage_hash(changed), field
