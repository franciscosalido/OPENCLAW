from __future__ import annotations

from pathlib import Path


SQL = Path("infra/postgres/sql/020_working_memory_checkpoints.sql")


def test_working_memory_checkpoint_schema_contract() -> None:
    sql = SQL.read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "create table if not exists working_memory_snapshots" in lowered
    assert "create table if not exists working_memory_snapshot_points" in lowered
    assert "uuidv7()" in lowered
    assert "memory_vector vector(768)" in lowered
    assert "snapshot_kind text not null check" in lowered
    assert "vector_dim integer not null check (vector_dim > 0)" in lowered
    assert "importance double precision check" in lowered
    assert "safe_summary text check" in lowered
    assert "idx_wm_snapshots_agent_session_created_at" in lowered
    assert "idx_wm_snapshot_points_payload_checksum" in lowered
    assert "hnsw" not in lowered
    assert "ivfflat" not in lowered
    for forbidden in ("prompt", "raw_prompt", "answer", "chunk_text", "document_text"):
        assert forbidden not in lowered
