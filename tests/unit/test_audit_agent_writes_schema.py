from __future__ import annotations

from pathlib import Path


MIGRATION = Path("backend/memory/postgres/migrations/021_create_audit_agent_writes.sql")
SPEC = Path("docs/specs/finlib-0/pr-04-audit-agent-writes.md")


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def _spec() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_migration_021_exists() -> None:
    assert MIGRATION.exists()


def test_migration_is_non_destructive_and_scoped() -> None:
    sql = _sql().lower()

    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "create schema" not in sql
    assert "audit." not in sql
    assert "ops." not in sql
    assert sql.count("create table if not exists") == 1
    assert "create table if not exists audit_agent_writes" in sql

    for forbidden in (
        "macro_series_catalog",
        "macro_observations",
        "treasury_",
        "fund_registry",
        "fund_daily_info",
        "fi_instruments",
        "debenture",
        "fundamentals_",
        "marketlibraryseederagent",
        "researchlibrarycuratoragent",
        "treasurymtagent",
        "pydanticai",
        "langgraph",
        "crewai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
    ):
        assert forbidden not in sql


def test_audit_agent_writes_core_contract() -> None:
    sql = _compact_sql()
    lower_sql = sql.lower()

    assert "audit_id UUID PRIMARY KEY DEFAULT uuidv7()" in sql
    assert "trace_id UUID NOT NULL" in sql
    assert "run_id UUID REFERENCES ops_ingestion_runs (run_id)" in sql
    assert "agent_id TEXT NOT NULL CHECK (agent_id ~ '\\S')" in sql
    assert "repository TEXT NOT NULL CHECK (repository ~ '\\S')" in sql
    assert "target_table TEXT NOT NULL CHECK (target_table ~ '\\S')" in sql
    assert "row_count INTEGER NOT NULL CHECK (row_count >= 0)" in sql
    assert "batch_hash TEXT NOT NULL CHECK (batch_hash ~ '\\S')" in sql
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in sql
    assert "metadata JSONB NOT NULL DEFAULT '{}'::JSONB" in sql
    assert "jsonb_typeof(metadata) = 'object'" in lower_sql


def test_operation_contract_excludes_delete() -> None:
    sql = _compact_sql()

    assert "operation TEXT NOT NULL" in sql
    for operation in ("insert", "update", "upsert", "bulk_insert", "bulk_upsert"):
        assert f"'{operation}'" in sql
    assert "'delete'" not in sql.lower()


def test_append_only_trigger_contract() -> None:
    sql = _compact_sql()

    assert "CREATE OR REPLACE FUNCTION prevent_audit_agent_writes_mutation()" in sql
    assert "RETURNS TRIGGER" in sql
    assert "RAISE EXCEPTION" in sql
    assert "append-only" in sql
    assert "CREATE OR REPLACE TRIGGER trg_audit_agent_writes_append_only" in sql
    assert "BEFORE UPDATE OR DELETE ON audit_agent_writes" in sql
    assert "EXECUTE FUNCTION prevent_audit_agent_writes_mutation()" in sql


def test_revoke_update_delete_from_public_is_present() -> None:
    sql = _compact_sql()

    assert "REVOKE UPDATE, DELETE ON audit_agent_writes FROM PUBLIC" in sql
    assert "trigger -- remains authoritative" in sql


def test_expected_indexes_are_focused() -> None:
    sql = _sql()

    assert "idx_audit_agent_writes_trace_id" in sql
    assert "ON audit_agent_writes (trace_id)" in sql
    assert "idx_audit_agent_writes_run_id" in sql
    assert "ON audit_agent_writes (run_id)" in sql
    assert "WHERE run_id IS NOT NULL" in sql
    assert "idx_audit_agent_writes_agent_created_at" in sql
    assert "ON audit_agent_writes (agent_id, created_at DESC)" in sql
    assert "idx_audit_agent_writes_repo_target_created_at" in sql
    assert "ON audit_agent_writes (repository, target_table, created_at DESC)" in sql
    assert "batch_hash)" not in sql


def test_no_forbidden_sensitive_columns_are_created() -> None:
    compact_table_body = _compact_sql().split(");", maxsplit=1)[0].lower()

    for forbidden in ("payload", "prompt", "chunk", "vector", "embedding", "dsn"):
        assert forbidden not in compact_table_body


def test_sdd_documents_future_transaction_contract() -> None:
    spec = _spec()

    assert "BEGIN;" in spec
    assert "insert exactly one audit_agent_writes row" in spec
    assert "If the audit insert fails, the domain write must roll back." in spec
    assert "Each logical batch must produce exactly one audit row." in spec
    assert "Corrections must be recorded as new rows." in spec
