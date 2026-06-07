from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.restore_service import RestoreService


NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.restored: list[WorkingMemoryPoint] = []
        self.deleted_scope: tuple[str, str] | None = None

    async def restore_points_from_snapshot(self, points: list[WorkingMemoryPoint]) -> int:
        self.restored.extend(points)
        return len(points)

    async def delete_session_points(self, *, agent_id: str, session_id: str) -> int:
        self.deleted_scope = (agent_id, session_id)
        return 1


class FakeRepository:
    def __init__(self, points: list[WorkingMemoryPoint]) -> None:
        self.points = points
        self.validated: str | None = None

    async def get_latest_snapshot(self, *, agent_id: str, session_id: str) -> dict[str, object] | None:
        return {"snapshot_id": "snap-1", "checksum": "ok", "agent_id": agent_id, "session_id": session_id}

    async def load_snapshot_points(self, snapshot_id: str) -> list[WorkingMemoryPoint]:
        return self.points

    async def validate_snapshot_checksum(self, snapshot_id: str) -> bool:
        self.validated = snapshot_id
        return True

    async def mark_snapshot_restored(self, snapshot_id: str) -> None:
        self.validated = snapshot_id


def _point() -> WorkingMemoryPoint:
    now = datetime.now(UTC)
    return WorkingMemoryPoint(
        point_id="p1",
        agent_id="agent",
        session_id=uuid4(),
        memory_kind="turn_summary",
        vector=(0.1, 0.2),
        vector_dim=2,
        importance=0.5,
        recency_ts=now,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=60),
        ttl_seconds=60,
        embedding_model="nomic",
    )


async def test_restore_merge_default_and_checksum() -> None:
    point = _point()
    store = FakeStore()
    repo = FakeRepository([point])
    service = RestoreService(store=store, repository=repo, replace_enabled=False)

    result = await service.restore_latest_snapshot(agent_id=point.agent_id, session_id=str(point.session_id))

    assert result.restored_count == 1
    assert result.checksum_ok is True
    assert store.deleted_scope is None
    assert store.restored == [point]


async def test_restore_replace_is_gated() -> None:
    point = _point()
    service = RestoreService(store=FakeStore(), repository=FakeRepository([point]), replace_enabled=False)

    with pytest.raises(ValueError, match="disabled"):
        await service.restore_snapshot("snap-1", agent_id=point.agent_id, session_id=str(point.session_id), replace=True)


async def test_restore_replace_deletes_only_agent_session_scope() -> None:
    point = _point()
    store = FakeStore()
    service = RestoreService(store=store, repository=FakeRepository([point]), replace_enabled=True)

    await service.restore_snapshot("snap-1", agent_id=point.agent_id, session_id=str(point.session_id), replace=True)

    assert store.deleted_scope == (point.agent_id, str(point.session_id))
