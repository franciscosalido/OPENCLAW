from __future__ import annotations

from pathlib import Path

from infra.postgres.pg_stat_report import build_degraded_report, redact_query_text


SQL = Path("infra/postgres/sql/010_pg_stat_statements_diagnostics.sql")


def test_pg_stat_sql_uses_safe_showtext_false_and_config_checks() -> None:
    sql = SQL.read_text(encoding="utf-8")

    assert "pg_stat_statements(showtext := false)" in sql
    for token in ("shared_preload_libraries", "compute_query_id", "pg_stat_statements.max", "pg_stat_statements.track", "track_io_timing"):
        assert token in sql
    assert "query text is intentionally omitted" in sql.lower()


def test_degraded_pg_stat_report_schema_omits_query_text() -> None:
    report = build_degraded_report(warning="unit")

    assert report["schema_version"] == "quimera-pg-stat-report-v1"
    assert report["pg_stat_statements"]["installed"] is False
    assert report["top_queries"] == []
    assert "query" not in str(report["top_queries"]).lower()
    assert "unit" in report["warnings"]


def test_redact_query_text_removes_literals() -> None:
    redacted = redact_query_text("SELECT * FROM sessions WHERE agent_id = 'secret-agent' AND session_id = 'abc'")

    assert "secret-agent" not in redacted
    assert "abc" not in redacted
    assert "sessions" in redacted
