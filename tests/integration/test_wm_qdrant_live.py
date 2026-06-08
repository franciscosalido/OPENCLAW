from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from backend.working_memory.config import WorkingMemorySettings
from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.qdrant_store import WorkingMemoryQdrantStore


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_wm_qdrant_live_upsert_query_list() -> None:
    if os.environ.get("QUIMERA_TEST_WM_QDRANT_LIVE") != "1":
        pytest.skip(
            "set QUIMERA_TEST_WM_QDRANT_LIVE=1 to run live Qdrant working-memory test"
        )
    settings = WorkingMemorySettings(
        collection_name=f"quimera_working_memory_test_{uuid4().hex}", vector_size=4
    )
    client = AsyncQdrantClient(url=settings.qdrant_url)
    store = WorkingMemoryQdrantStore(client, settings)
    await store.ensure_collection()
    session_id = uuid4()
    now = datetime.now(UTC)
    point = WorkingMemoryPoint(
        point_id=f"wm-{uuid4().hex}",
        agent_id="agent-live",
        session_id=session_id,
        memory_kind="turn_summary",
        vector=(0.1, 0.2, 0.3, 0.4),
        vector_dim=4,
        recency_ts=now,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=60),
        ttl_seconds=60,
        embedding_model="nomic-embed-text",
        safe_summary="live safe summary",
    )
    await store.upsert_memory_point(point)

    results = await store.query_working_memory(
        agent_id=point.agent_id, session_id=str(session_id), query_vector=point.vector
    )
    listed = await store.list_session_memory(
        agent_id=point.agent_id, session_id=str(session_id)
    )

    assert results
    assert listed
    assert "vector" not in results[0]
    await store.delete_session_points(
        agent_id=point.agent_id, session_id=str(session_id)
    )
