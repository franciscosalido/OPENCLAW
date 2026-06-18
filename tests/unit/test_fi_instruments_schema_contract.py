from __future__ import annotations

from pathlib import Path


MIGRATION = Path("backend/memory/postgres/migrations/025_create_fi_instruments.sql")
SDD = Path("docs/specs/finlib-0/pr-08-private-fixed-income.md")

EXPECTED_KINDS = ("cdb", "lca", "lci", "cri", "cra", "debenture")
EXPECTED_INDEXERS = ("cdi", "ipca", "prefixado", "selic", "igpm")
LEVEL0_FORBIDDEN_FIELDS = (
    "quantity",
    "face_value_held",
    "acquisition_price",
    "yield_at_purchase",
    "custodian",
    "account_number",
    "cpf",
    "holder_id",
    "portfolio_id",
    "broker_id",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def test_migration_025_exists_and_is_non_destructive() -> None:
    sql = _sql().lower()

    assert MIGRATION.exists()
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "alter table" not in sql
    assert "create schema" not in sql
    assert "fi." not in sql
    assert "market." not in sql
    assert "ops." not in sql
    assert "audit." not in sql


def test_migration_scope_is_limited_to_fi_instruments() -> None:
    lower_sql = _sql().lower()

    assert lower_sql.count("create table if not exists") == 1
    assert "create table if not exists fi_instruments" in lower_sql

    for forbidden in (
        "fi_positions",
        "debenture_market_data",
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
        "download",
        "httpx",
        "requests",
        "fetch",
    ):
        assert forbidden not in lower_sql


def test_ops_sources_are_seeded_without_extending_source_kind_domain() -> None:
    compact = _compact_sql()

    assert compact.count("INSERT INTO ops_data_sources") == 2
    assert "'local_fixed_income_input'" in compact
    assert "'user_supplied'" in compact
    assert "'anbima_debentures'" in compact
    assert "'market_data_vendor'" in compact
    assert "ON CONFLICT (source_id) DO UPDATE SET" in compact
    assert "local_extract" not in compact
    assert "industry_association" not in compact


def test_fi_instruments_identity_and_reference_contract() -> None:
    compact = _compact_sql()

    assert "instrument_id UUID PRIMARY KEY DEFAULT uuidv7()" in compact
    assert "issuer_cnpj TEXT NOT NULL CHECK (issuer_cnpj ~ '^[0-9]{14}$')" in compact
    assert "issuer_name TEXT NOT NULL CHECK (issuer_name ~ '\\S')" in compact
    assert "instrument_name TEXT CHECK (" in compact
    assert "instrument_name IS NULL OR instrument_name ~ '\\S'" in compact
    assert (
        "isin TEXT UNIQUE CHECK (isin IS NULL OR isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$')"
        in compact
    )
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "run_id UUID REFERENCES ops_ingestion_runs (run_id)" in compact


def test_kind_and_indexer_domains_are_complete() -> None:
    compact = _compact_sql()

    for kind in EXPECTED_KINDS:
        assert f"'{kind}'" in compact
    for indexer in EXPECTED_INDEXERS:
        assert f"'{indexer}'" in compact


def test_rate_spec_jsonb_shape_contract() -> None:
    compact = _compact_sql()

    assert "rate_spec JSONB NOT NULL" in compact
    assert "jsonb_typeof(rate_spec) = 'object'" in compact
    for key in ("indexer", "rate_model", "day_count", "payment_frequency"):
        assert f"rate_spec ? '{key}'" in compact


def test_fgc_maturity_and_lineage_contracts() -> None:
    compact = _compact_sql()

    assert "fgc_covered BOOLEAN NOT NULL DEFAULT FALSE" in compact
    assert "kind NOT IN ('cri', 'cra', 'debenture') OR fgc_covered = FALSE" in compact
    assert (
        "kind NOT IN ('cri', 'cra', 'debenture') OR maturity_date IS NOT NULL"
        in compact
    )
    assert (
        "maturity_date IS NULL OR issue_date IS NULL OR maturity_date >= issue_date"
        in compact
    )
    assert "lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\\S')" in compact
    assert "UNIQUE (lineage_hash)" in compact
    assert (
        "UNIQUE (kind, issuer_cnpj, indexer, maturity_date, lineage_hash)"
        not in compact
    )


def test_jsonb_and_text_constraints_are_strict() -> None:
    compact = _compact_sql()

    assert "btrim(" not in compact.lower()
    assert "~ '\\S'" in compact
    assert "CHECK (jsonb_typeof(quality_flags) = 'object')" in compact
    assert "CHECK (jsonb_typeof(metadata) = 'object')" in compact


def test_indexes_are_small_and_target_catalog_lookup() -> None:
    compact = _compact_sql()

    assert "idx_fi_instruments_kind_indexer" in compact
    assert "idx_fi_instruments_issuer_cnpj" in compact
    assert "idx_fi_instruments_source_id" in compact
    assert (
        "CONCURRENTLY is prohibited inside the transactional migration runner" in _sql()
    )


def test_migration_excludes_level0_position_fields() -> None:
    lower_sql = _sql().lower()

    for field in LEVEL0_FORBIDDEN_FIELDS:
        assert field not in lower_sql


def test_sdd_documents_level0_boundary_and_lineage_contract() -> None:
    sdd = SDD.read_text(encoding="utf-8")

    assert "REFERENCE CATALOG" in sdd
    assert "Level 0" in sdd
    assert "fi_positions" in sdd
    assert "must not be sent to remote providers" in sdd
    assert "does not download" in sdd
    assert "lineage_hash" in sdd
    for field in LEVEL0_FORBIDDEN_FIELDS:
        assert field in sdd
