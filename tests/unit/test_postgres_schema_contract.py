from __future__ import annotations

from pathlib import Path


SCHEMA = Path("backend/memory/postgres/schema.sql")


def _schema_sql() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_schema_sql_contains_all_pr01_tables() -> None:
    sql = _schema_sql()
    for table in ("sessions", "turns", "agent_states", "entity_mentions"):
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert table in sql


def test_all_pr01_tables_have_primary_keys() -> None:
    assert _schema_sql().count("PRIMARY KEY") >= 5


def test_schema_contains_required_foreign_keys_and_cascades() -> None:
    sql = _schema_sql()
    assert "REFERENCES sessions(session_id) ON DELETE CASCADE" in sql
    assert "REFERENCES turns(turn_id) ON DELETE CASCADE" in sql
    assert sql.count("ON DELETE CASCADE") >= 3


def test_schema_contains_role_and_confidence_checks() -> None:
    sql = _schema_sql()
    assert "role IN ('user','assistant','system','tool')" in sql
    assert "confidence >= 0.0" in sql
    assert "confidence <= 1.0" in sql


def test_schema_uses_jsonb_and_timestamptz() -> None:
    sql = _schema_sql()
    assert "metadata     JSONB" in sql
    assert "state_value     JSONB" in sql
    assert sql.count("TIMESTAMPTZ") >= 5


def test_schema_contains_required_indexes() -> None:
    sql = _schema_sql()
    required_indexes = (
        "idx_sessions_agent_id",
        "idx_sessions_created_at",
        "idx_sessions_agent_created_at",
        "idx_sessions_user_id",
        "idx_turns_session_id",
        "idx_turns_created_at",
        "idx_turns_session_created_at",
        "idx_agent_states_agent_id",
        "idx_agent_states_session_id",
        "idx_agent_states_updated_at",
        "idx_agent_states_agent_session",
        "idx_entity_mentions_turn_id",
        "idx_entity_mentions_entity_text",
        "idx_entity_mentions_entity_type",
    )
    for index_name in required_indexes:
        assert index_name in sql


def test_schema_contains_sessions_updated_at_trigger() -> None:
    sql = _schema_sql()
    assert "CREATE OR REPLACE FUNCTION set_updated_at()" in sql
    assert "CREATE TRIGGER trg_sessions_updated_at" in sql
