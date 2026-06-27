from __future__ import annotations

from pathlib import Path


MIGRATION = Path(
    "backend/memory/postgres/migrations/028_create_company_fundamentals.sql"
)
PREVIOUS_MIGRATION = Path(
    "backend/memory/postgres/migrations/027_guard_debenture_kind_drift.sql"
)
SDD = Path("docs/specs/finlib-0/pr-10-company-fundamentals.md")

LEVEL0_FORBIDDEN_FIELDS = (
    "quantity",
    "position_size",
    "acquisition_price",
    "yield_at_purchase",
    "cost_basis",
    "custodian",
    "account_number",
    "broker_id",
    "cpf",
    "holder_id",
    "portfolio_id",
    "user_id",
    "personal_notes",
    "recommendation",
    "target_weight",
)

FORBIDDEN_SCOPE_TERMS = (
    "create table if not exists repositories",
    "create table if not exists agents",
    "httpx",
    "requests",
    "download",
    "client_secret",
    "api_key",
    "bearer_token",
    "credentials",
    "qdrant",
    "pgvector",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def _sdd() -> str:
    return SDD.read_text(encoding="utf-8")


def _table_sql(table_name: str) -> str:
    lower_sql = _sql().lower()
    start = lower_sql.index(f"create table if not exists {table_name}")
    next_start = lower_sql.find("create table if not exists", start + 1)
    if next_start == -1:
        return lower_sql[start:]
    return lower_sql[start:next_start]


def test_migration_028_exists_and_does_not_reuse_027() -> None:
    assert PREVIOUS_MIGRATION.exists()
    assert MIGRATION.exists()
    assert "028_create_company_fundamentals" in MIGRATION.stem
    assert "027_create_company_fundamentals" not in MIGRATION.name


def test_migration_is_additive_and_limited_to_four_tables() -> None:
    lower_sql = _sql().lower()

    assert "drop table" not in lower_sql
    assert "truncate" not in lower_sql
    assert "create schema" not in lower_sql
    assert lower_sql.count("create table if not exists") == 4
    for table_name in (
        "company_registry",
        "company_listings",
        "fundamentals_statements",
        "fundamentals_indicators",
    ):
        assert f"create table if not exists {table_name}" in lower_sql
    for forbidden in FORBIDDEN_SCOPE_TERMS:
        assert forbidden not in lower_sql


def test_level0_and_secret_fields_are_absent_from_schema() -> None:
    lower_sql = _sql().lower()

    for field in LEVEL0_FORBIDDEN_FIELDS:
        assert field not in lower_sql
    assert "client_secret" not in lower_sql
    assert "api_key" not in lower_sql


def test_company_registry_contract() -> None:
    compact = _compact_sql()
    registry_sql = _table_sql("company_registry")

    assert "company_id UUID PRIMARY KEY DEFAULT uuidv7()" in compact
    assert "cnpj TEXT NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$')" in compact
    assert "cnpj_base TEXT NOT NULL CHECK (cnpj_base ~ '^[0-9]{8}$')" in compact
    assert (
        "cvm_code TEXT UNIQUE CHECK (cvm_code IS NULL OR cvm_code ~ '\\S')" in compact
    )
    assert "CHECK (cnpj_base = substring(cnpj FROM 1 FOR 8))" in compact
    assert "idx_company_registry_cnpj_base" in compact
    assert "ticker" not in registry_sql


def test_company_listings_contract() -> None:
    compact = _compact_sql()

    assert (
        "company_id UUID NOT NULL REFERENCES company_registry (company_id)" in compact
    )
    assert (
        "exchange TEXT NOT NULL CHECK (exchange IN ('B3', 'NYSE', 'NASDAQ', 'OTHER'))"
        in compact
    )
    assert "ticker TEXT NOT NULL CHECK (ticker ~ '^[A-Z]{4}[0-9]{1,2}$')" in compact
    assert (
        "share_class TEXT NOT NULL CHECK (share_class IN ('ON', 'PN', 'UNT', 'BDR', 'OTHER'))"
        in compact
    )
    assert (
        "isin TEXT UNIQUE CHECK (isin IS NULL OR isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$')"
        in compact
    )
    assert "UNIQUE (exchange, ticker)" in compact
    assert "UNIQUE (ticker)" not in compact


def test_fundamentals_statements_contract() -> None:
    compact = _compact_sql()

    assert "period_type TEXT NOT NULL CHECK (period_type IN ('DFP', 'ITR'))" in compact
    assert (
        "period_kind TEXT NOT NULL CHECK (period_kind IN ('annual', 'quarterly'))"
        in compact
    )
    assert (
        "statement_scope TEXT NOT NULL CHECK (statement_scope IN ('consolidated', 'individual'))"
        in compact
    )
    assert "version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)" in compact
    assert (
        "prior_version_id UUID REFERENCES fundamentals_statements (statement_id)"
        in compact
    )
    assert (
        "restatement_reason TEXT CHECK (restatement_reason IS NULL OR restatement_reason ~ '\\S')"
        in compact
    )
    assert (
        "statements_json JSONB NOT NULL CHECK (jsonb_typeof(statements_json) = 'object')"
        in compact
    )
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id)" in compact
    assert "lineage_hash TEXT NOT NULL UNIQUE CHECK (lineage_hash ~ '\\S')" in compact
    assert (
        "period_type = 'DFP' AND period_kind = 'annual' AND fiscal_quarter IS NULL"
        in compact
    )
    assert (
        "period_type = 'ITR' AND period_kind = 'quarterly' AND fiscal_quarter BETWEEN 1 AND 4"
        in compact
    )
    assert (
        "version = 1 AND prior_version_id IS NULL AND restatement_reason IS NULL"
        in compact
    )
    assert (
        "version > 1 AND prior_version_id IS NOT NULL AND restatement_reason IS NOT NULL"
        in compact
    )


def test_fundamentals_indicators_hypertable_contract() -> None:
    compact = _compact_sql()

    assert "CREATE TABLE IF NOT EXISTS fundamentals_indicators" in compact
    assert "ts TIMESTAMPTZ NOT NULL" in compact
    assert (
        "source_statement_id UUID NOT NULL REFERENCES fundamentals_statements (statement_id)"
        in compact
    )
    assert "PRIMARY KEY (company_id, ts, indicator_set, source_statement_id)" in compact
    assert "UNIQUE (lineage_hash, ts)" in compact
    assert "UNIQUE (lineage_hash)" not in compact
    assert "SELECT create_hypertable(" in compact
    assert "'fundamentals_indicators'" in compact
    assert "'ts'" in compact
    assert "chunk_time_interval => INTERVAL '3 months'" in compact
    assert "if_not_exists => TRUE" in compact
    assert _sql().count("create_hypertable(") == 1


def test_jsonb_text_and_source_contracts() -> None:
    compact = _compact_sql()
    lower_sql = _sql().lower()

    for expression in (
        "jsonb_typeof(metadata) = 'object'",
        "jsonb_typeof(quality_flags) = 'object'",
        "jsonb_typeof(statements_json) = 'object'",
        "jsonb_typeof(indicators_json) = 'object'",
    ):
        assert expression in compact
    assert "btrim(" not in lower_sql
    for source_id in (
        "cvm_cia_aberta_cadastro",
        "cvm_dfp",
        "cvm_itr",
        "b3_listings",
    ):
        assert source_id in lower_sql
    assert "kind = excluded.kind" not in lower_sql
    assert "base_url = excluded.base_url" not in lower_sql
    assert "enabled = excluded.enabled" not in lower_sql
    assert "metadata = ops_data_sources.metadata || excluded.metadata" in lower_sql


def test_sdd_documents_required_boundaries() -> None:
    sdd = _sdd().lower()

    for expected in (
        "migration 028",
        "petr3",
        "petr4",
        "versioned statements",
        "statement-only",
        "market-dependent",
        "hypertable",
        "level 0",
        "future repository transaction contract",
        "advisory lock",
        "sandbox",
        "rollback",
    ):
        assert expected in sdd
