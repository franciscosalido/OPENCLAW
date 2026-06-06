from __future__ import annotations

from pathlib import Path


ADR = Path("docs/ADR/ADR-004-working-memory-checkpoint-contract.md")
CONTRACT = Path("docs/04_MEM/WORKING_MEMORY_CONTRACT.md")
SQL = Path("infra/postgres/sql/011_working_memory_checkpoint_contract.sql")


def test_working_memory_adr_is_accepted_without_backend_decision() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "Status: Accepted" in text
    assert "backend fast layer deferred" in text.lower()
    assert "pgvector" in text
    assert "durable checkpoint" in text.lower()
    assert "redis as final backend" not in text.lower()
    assert "python in-process as final backend" not in text.lower()
    assert "qdrant in-memory as final backend" not in text.lower()


def test_working_memory_contract_doc_exists_and_blocks_hot_source_of_truth() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "fast layer backend is deferred" in text.lower()
    assert "pgvector checkpoint" in text.lower()
    assert "no RAM layer is a source of truth" in text
    assert "checkpoint + canonical memory" in text
    assert "prompt" in text.lower()
    assert "response" in text.lower()
    assert "chunk" in text.lower()


def test_working_memory_checkpoint_sql_contract() -> None:
    sql = SQL.read_text(encoding="utf-8")

    for token in ("working_memory_checkpoints", "agent_id", "session_id", "embedding_model", "checksum", "ttl_seconds", "expires_at"):
        assert token in sql
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "UNIQUE(agent_id, session_id, topic, embedding_model, checksum)" in sql
    assert "vector" in sql
    assert "prompt" not in sql.lower()
    assert "answer" not in sql.lower()
    assert "chunk_text" not in sql.lower()
    assert "CREATE INDEX IF NOT EXISTS idx_working_memory_agent_session_created_at" in sql
