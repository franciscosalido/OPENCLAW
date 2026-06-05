from __future__ import annotations

from pathlib import Path


CLIENT = Path("integration/agentic0_client.py")


def test_agentic0_client_has_no_direct_backend_access() -> None:
    text = CLIENT.read_text(encoding="utf-8")

    assert "asyncpg" not in text
    assert "qdrant_client" not in text
    assert "QUIMERA_POSTGRES_DSN" not in text
    assert "TEST_POSTGRES_DSN" not in text
    assert "psycopg" not in text
    assert "psql" not in text
    assert "127.0.0.1:11434" not in text
    assert "127.0.0.1:6333" not in text
    assert "litellm_base_url" in text
