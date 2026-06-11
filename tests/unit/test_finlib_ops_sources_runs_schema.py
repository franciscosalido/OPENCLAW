from __future__ import annotations

from pathlib import Path


MIGRATION = Path("backend/memory/postgres/migrations/019_create_ops_sources_runs.sql")


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def test_migration_019_exists_in_postgres_migrations_dir() -> None:
    assert MIGRATION.exists()


def test_migration_is_non_destructive_and_stays_in_public_prefix_convention() -> None:
    sql = _sql().lower()

    assert "drop table" not in sql
    assert "create schema" not in sql
    assert "ops." not in sql
    assert "create table if not exists ops_ingestion_watermarks" not in sql
    assert "create table if not exists ops_data_quality_checks" not in sql
    assert "create table if not exists ops_outbox_events" not in sql
    assert "create table if not exists audit_agent_writes" not in sql
    assert "agent" not in sql.replace("agent_id", "")
    assert "agent" not in "".join(
        line for line in sql.splitlines() if line.startswith("create table")
    )


def test_migration_creates_exact_ops_tables_for_pr02() -> None:
    sql = _sql()

    assert "CREATE TABLE IF NOT EXISTS ops_data_sources" in sql
    assert "CREATE TABLE IF NOT EXISTS ops_ingestion_runs" in sql
    assert sql.count("CREATE TABLE IF NOT EXISTS ops_") == 2


def test_ops_data_sources_contract() -> None:
    sql = _compact_sql()
    lower_sql = sql.lower()

    assert "source_id TEXT PRIMARY KEY" in sql
    assert "kind TEXT NOT NULL" in sql
    assert "methodology_limitations TEXT NOT NULL" in sql
    assert "enabled BOOLEAN NOT NULL DEFAULT TRUE" in sql
    assert "metadata JSONB NOT NULL DEFAULT '{}'::JSONB" in sql
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in sql
    assert "source_id ~ '^[a-z0-9_.:-]+$'" in sql
    assert "length(source_id) <= 128" in sql
    assert "jsonb_typeof(metadata) = 'object'" in lower_sql


def test_b3_historical_quotes_limitation_is_seeded_as_data() -> None:
    sql = _sql()

    assert "b3_cotacoes_historicas" in sql
    assert "https://www.b3.com.br/pt_br/market-data-e-indices/" in sql
    assert "sem ajuste por inflação" in sql
    assert "proventos corporativos" in sql
    assert "'country', 'BR'" in sql
    assert "'source_family', 'historical_quotes'" in sql


def test_ops_ingestion_runs_contract() -> None:
    sql = _compact_sql()

    assert "run_id UUID PRIMARY KEY DEFAULT uuidv7()" in sql
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in sql
    assert "agent_id TEXT NOT NULL" in sql
    assert "trace_id UUID NOT NULL" in sql
    assert "metadata JSONB NOT NULL DEFAULT '{}'::JSONB" in sql
    assert "mode IN ('dry_run', 'execute')" in sql
    assert "status IN ('created', 'running', 'completed', 'failed', 'cancelled')" in sql


def test_ops_ingestion_runs_quality_constraints() -> None:
    sql = _compact_sql()

    for counter in (
        "records_seen",
        "records_inserted",
        "records_updated",
        "records_rejected",
    ):
        assert f"{counter} INTEGER NOT NULL DEFAULT 0" in sql
        assert f"{counter} >= 0" in sql
    assert "finished_at IS NULL OR finished_at >= started_at" in sql
    assert "source_snapshot_hash IS NULL OR source_snapshot_hash ~ '\\S'" in sql
    assert "NOT (mode = 'execute' AND status = 'completed')" in sql
    assert (
        "OR (source_snapshot_hash IS NOT NULL AND source_snapshot_hash ~ '\\S')" in sql
    )


def test_ops_text_constraints_use_non_whitespace_regex_not_btrim() -> None:
    sql = _sql()
    compact_sql = _compact_sql()

    assert "length(btrim(source_id))" not in sql
    assert "methodology_limitations ~ '\\S'" in sql
    assert "agent_id TEXT NOT NULL CHECK (agent_id ~ '\\S')" in sql
    assert "source_snapshot_hash IS NULL OR source_snapshot_hash ~ '\\S'" in compact_sql
    assert "error_summary IS NULL OR error_summary ~ '\\S'" in compact_sql
    assert "length(btrim(methodology_limitations))" not in sql
    assert "length(btrim(agent_id))" not in sql
    assert "length(btrim(source_snapshot_hash))" not in sql
    assert "length(btrim(error_summary))" not in sql
    assert "nullif(btrim(source_snapshot_hash), '')" not in sql


def test_ops_ingestion_runs_indexes_are_focused() -> None:
    sql = _sql()

    assert "idx_ops_ingestion_runs_source_started_at" in sql
    assert "ON ops_ingestion_runs (source_id, started_at DESC)" in sql
    assert "idx_ops_ingestion_runs_trace_id" in sql
    assert "ON ops_ingestion_runs (trace_id)" in sql
    assert "idx_ops_ingestion_runs_status_started_at" in sql
    assert "ON ops_ingestion_runs (status, started_at DESC)" in sql


def test_migration_avoids_forbidden_framework_or_agent_scope() -> None:
    sql = _sql().lower()

    for forbidden in (
        "langchain",
        "pydanticai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
        "marketlibraryseederagent",
        "researchlibrarycuratoragent",
        "treasurymtagent",
    ):
        assert forbidden not in sql
