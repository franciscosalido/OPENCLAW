from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any


MIGRATION = Path(
    "backend/memory/postgres/migrations/023_create_treasury_bonds_prices.sql"
)
SDD = Path("docs/specs/finlib-0/pr-06-treasury-library.md")

EXPECTED_BOND_TYPES = {
    "Tesouro_Selic",
    "Tesouro_IPCA+",
    "Tesouro_IPCA+_Juros_Semestrais",
    "Tesouro_Prefixado",
    "Tesouro_Prefixado_Juros_Semestrais",
    "Tesouro_Renda+",
    "Tesouro_Educa+",
}
EXPECTED_SECURITY_FAMILIES = {
    "LFT",
    "LTN",
    "NTN-B",
    "NTN-B_Principal",
    "NTN-F",
    "OTHER",
}
LINEAGE_FIELDS = (
    "bond_type",
    "maturity_date",
    "ts",
    "price_bid",
    "price_ask",
    "rate_bid",
    "rate_ask",
    "base_value",
    "source_id",
    "schema_version",
)
CSV_SAMPLE = """Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha
Tesouro Selic;01/03/2029;12/06/2026;10,35;10,25;15000,12;15001,34;14999,00
"""


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def _decimal_br(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def _date_br(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def _normalize_bond_type(value: str) -> str:
    mapping = {
        "Tesouro Selic": "Tesouro_Selic",
        "Tesouro IPCA+": "Tesouro_IPCA+",
        "Tesouro IPCA+ com Juros Semestrais": ("Tesouro_IPCA+_Juros_Semestrais"),
        "Tesouro Prefixado": "Tesouro_Prefixado",
        "Tesouro Prefixado com Juros Semestrais": (
            "Tesouro_Prefixado_Juros_Semestrais"
        ),
        "Tesouro RendA+": "Tesouro_Renda+",
        "Tesouro Educa+": "Tesouro_Educa+",
    }
    return mapping[value]


def _lineage_hash(row: dict[str, Any]) -> str:
    payload = {field: str(row[field]) for field in LINEAGE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sample_row() -> dict[str, Any]:
    parsed = next(csv.DictReader(StringIO(CSV_SAMPLE), delimiter=";"))
    maturity = _date_br(parsed["Data Vencimento"])
    ref_ts = datetime.combine(
        _date_br(parsed["Data Base"]), datetime.min.time(), tzinfo=timezone.utc
    )
    row: dict[str, Any] = {
        "bond_type": _normalize_bond_type(parsed["Tipo Titulo"]),
        "maturity_date": maturity.isoformat(),
        "ts": ref_ts.isoformat(),
        "price_bid": _decimal_br(parsed["PU Compra Manha"]),
        "price_ask": _decimal_br(parsed["PU Venda Manha"]),
        "rate_bid": _decimal_br(parsed["Taxa Compra Manha"]),
        "rate_ask": _decimal_br(parsed["Taxa Venda Manha"]),
        "base_value": _decimal_br(parsed["PU Base Manha"]),
        "source_id": "tesouro_transparente",
        "schema_version": 1,
    }
    row["lineage_hash"] = _lineage_hash(row)
    return row


def test_migration_023_exists_and_is_non_destructive() -> None:
    sql = _sql().lower()

    assert MIGRATION.exists()
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "create schema" not in sql
    assert "treasury." not in sql


def test_migration_scope_is_limited_to_treasury_objects() -> None:
    lower_sql = _sql().lower()

    assert lower_sql.count("create table if not exists") == 2
    assert "create table if not exists treasury_bonds" in lower_sql
    assert "create table if not exists treasury_prices" in lower_sql

    for forbidden in (
        "create or replace view",
        "macro_series_catalog",
        "macro_observations",
        "fund_registry",
        "fund_daily_info",
        "fi_instruments",
        "debenture",
        "fundamentals_",
        "repository",
        "pydanticai",
        "langgraph",
        "crewai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
    ):
        assert forbidden not in lower_sql


def test_migration_seeds_tesouro_transparente_source_as_treasury() -> None:
    compact = _compact_sql()

    assert "INSERT INTO ops_data_sources" in compact
    assert "'tesouro_transparente'" in compact
    assert "'treasury'" in compact
    assert "'government_treasury'" not in compact
    assert "ON CONFLICT (source_id) DO UPDATE SET" in compact


def test_treasury_bonds_contract() -> None:
    compact = _compact_sql()

    assert "bond_id UUID PRIMARY KEY DEFAULT uuidv7()" in compact
    assert "maturity_date DATE NOT NULL" in compact
    assert "display_name TEXT NOT NULL CHECK (display_name ~ '\\S')" in compact
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in compact
    assert "UNIQUE (bond_type, maturity_date)" in compact
    assert "CHECK (jsonb_typeof(metadata) = 'object')" in compact
    for bond_type in EXPECTED_BOND_TYPES:
        assert f"'{bond_type}'" in compact
    for family in EXPECTED_SECURITY_FAMILIES:
        assert f"'{family}'" in compact


def test_treasury_prices_contract_and_provenance() -> None:
    compact = _compact_sql()

    assert "bond_id UUID NOT NULL REFERENCES treasury_bonds (bond_id)" in compact
    assert "ts TIMESTAMPTZ NOT NULL" in compact
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id)" in compact
    assert "lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\\S')" in compact
    assert (
        "schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0)"
        in compact
    )
    assert "PRIMARY KEY (bond_id, ts)" in compact
    assert "UNIQUE (lineage_hash, ts)" in compact


def test_treasury_prices_quality_constraints() -> None:
    compact = _compact_sql()

    assert "price_bid NUMERIC CHECK (price_bid IS NULL OR price_bid >= 0)" in compact
    assert "price_ask NUMERIC CHECK (price_ask IS NULL OR price_ask >= 0)" in compact
    assert "base_value NUMERIC CHECK (base_value IS NULL OR base_value >= 0)" in compact
    assert "rate_bid NUMERIC" in compact
    assert "rate_ask NUMERIC" in compact
    assert "rate_bid NUMERIC CHECK" not in compact
    assert "rate_ask NUMERIC CHECK" not in compact
    assert "OR base_value IS NOT NULL" in compact
    assert "price_ask IS NULL OR price_bid IS NULL OR price_ask >= price_bid" in compact
    assert "rate_bid IS NULL OR rate_ask IS NULL OR rate_bid >= rate_ask" in compact
    assert "date_trunc('day', now() AT TIME ZONE 'UTC')" in compact


def test_migration_uses_regex_text_constraints_not_btrim() -> None:
    compact = _compact_sql()

    assert "btrim(" not in compact.lower()
    assert "~ '\\S'" in compact


def test_migration_hypertable_contract() -> None:
    compact = _compact_sql()

    assert "SELECT create_hypertable(" in compact
    assert "'treasury_prices'" in compact
    assert "'ts'" in compact
    assert "chunk_time_interval => INTERVAL '1 month'" in compact
    assert "if_not_exists => TRUE" in compact
    assert "idx_treasury_bonds_type_maturity" in compact
    assert "idx_treasury_prices_bond_ts_desc" in compact
    assert "idx_treasury_prices_source_run" in compact
    assert (
        "CONCURRENTLY is prohibited inside the transactional migration runner" in _sql()
    )


def test_jsonb_fields_are_object_constrained() -> None:
    compact = _compact_sql()

    assert compact.count("CHECK (jsonb_typeof(metadata) = 'object')") == 2
    assert "CHECK (jsonb_typeof(quality_flags) = 'object')" in compact


def test_csv_sample_round_trips_to_normalized_treasury_row() -> None:
    row = _sample_row()

    assert row["bond_type"] == "Tesouro_Selic"
    assert row["maturity_date"] == "2029-03-01"
    assert row["ts"] == "2026-06-12T00:00:00+00:00"
    assert row["price_bid"] == Decimal("15000.12")
    assert row["price_ask"] == Decimal("15001.34")
    assert row["rate_bid"] == Decimal("10.35")
    assert row["rate_ask"] == Decimal("10.25")
    assert row["base_value"] == Decimal("14999.00")
    assert len(str(row["lineage_hash"])) == 64


def test_lineage_hash_changes_when_maturity_date_changes() -> None:
    row = _sample_row()
    changed = dict(row)
    changed["maturity_date"] = "2030-03-01"

    assert _lineage_hash(row) != _lineage_hash(changed)


def test_sdd_documents_source_time_spread_and_future_repository_contract() -> None:
    sdd = SDD.read_text(encoding="utf-8")

    assert "kind = 'treasury'" in sdd
    assert "government_treasury" in sdd
    assert "daily CSV" in sdd
    assert "YYYY-MM-DD 00:00:00+00" in sdd
    assert "price_bid" in sdd
    assert "price_ask" in sdd
    assert "rate_bid >= rate_ask" in sdd
    assert "UNIQUE (lineage_hash, ts)" in sdd
    assert "TimescaleDB unique constraints" in sdd
    assert "no `revision` column" in sdd
    assert "corrected observation for an existing `(bond_id, ts)`" in sdd
    assert "audited" in sdd
    assert "audit_agent_writes" in sdd
