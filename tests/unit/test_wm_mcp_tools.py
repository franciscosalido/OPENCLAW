from __future__ import annotations

from uuid import uuid4
from typing import Any, cast

import pytest

from backend.mcp.working_memory_tools import (
    build_working_memory_health,
    working_memory_cleanup_expired,
    working_memory_query,
    working_memory_restore,
    working_memory_upsert,
)
from backend.working_memory.config import WorkingMemorySettings


async def test_working_memory_tools_validate_inputs_and_hide_vectors() -> None:
    session_id = str(uuid4())
    settings = WorkingMemorySettings(
        vector_size=3, collection_name="quimera_working_memory_test_mcp"
    )

    response = await working_memory_upsert(
        agent_id="agent",
        session_id=session_id,
        memory_kind="turn_summary",
        vector=[0.1, 0.2, 0.3],
        metadata={"safe": True},
        safe_summary="ok",
        settings=settings,
        store=None,
    )

    assert response["ok"] is True
    assert "vector" not in str(response).lower()
    assert "payload" not in str(response).lower()


async def test_working_memory_query_limit_and_restore_cleanup_gates() -> None:
    session_id = str(uuid4())
    settings = WorkingMemorySettings(
        vector_size=3, collection_name="quimera_working_memory_test_mcp"
    )

    with pytest.raises(ValueError, match="limit"):
        await working_memory_query(
            "agent",
            session_id,
            [0.1, 0.2, 0.3],
            limit=100,
            settings=settings,
            store=None,
        )

    restore = await working_memory_restore(
        "agent", session_id, settings=settings, restore_service=None
    )
    cleanup = await working_memory_cleanup_expired(
        settings=settings, cleanup_service=None
    )

    assert restore["ok"] is False
    assert "disabled" in str(restore["error"])
    assert cleanup["ok"] is False
    assert "disabled" in str(cleanup["error"])


def test_working_memory_health_contract() -> None:
    response = build_working_memory_health(WorkingMemorySettings())

    details = cast(dict[str, Any], response["details"])
    assert response["schema_version"] == "quimera-mcp-health-v1"
    assert response["backend"] == "working_memory"
    assert details["collection"] == "quimera_working_memory"
