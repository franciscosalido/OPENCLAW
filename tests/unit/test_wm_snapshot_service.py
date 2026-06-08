from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.working_memory import snapshot_service
from backend.working_memory.checkpoint_repository import (
    WorkingMemoryCheckpointRepository,
)
from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.snapshot_service import (
    SnapshotService,
    compute_snapshot_checksum,
)


NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
SESSION_ID = UUID("00000000-0000-0000-0000-000000000123")


def _point(point_id: str, *, expired: bool = False) -> WorkingMemoryPoint:
    created_at = NOW - timedelta(seconds=120) if expired else NOW
    return WorkingMemoryPoint(
        point_id=point_id,
        agent_id="agent",
        session_id=SESSION_ID,
        memory_kind="turn_summary",
        vector=(0.1, 0.2),
        vector_dim=2,
        importance=0.5,
        recency_ts=NOW,
        created_at=created_at,
        updated_at=created_at,
        expires_at=NOW - timedelta(seconds=1)
        if expired
        else NOW + timedelta(seconds=60),
        ttl_seconds=60,
        embedding_model="nomic",
    )


class FakeStore:
    def __init__(self, points: list[WorkingMemoryPoint]) -> None:
        self.points = points
        self.checkpointed: tuple[list[str], str] | None = None

    async def export_session_points_for_snapshot(
        self, *, agent_id: str, session_id: str, limit: int | None = None
    ) -> list[WorkingMemoryPoint]:
        return self.points

    async def mark_checkpointed(
        self, *, point_ids: Iterable[str], checkpoint_id: str
    ) -> None:
        self.checkpointed = (list(point_ids), checkpoint_id)


class FakeRepository:
    def __init__(self) -> None:
        self.header_kwargs: dict[str, object] | None = None

    async def create_snapshot_header(self, **kwargs: object) -> str:
        self.header_kwargs = kwargs
        return "snapshot-1"

    async def insert_snapshot_points(
        self, *, snapshot_id: str, points: list[WorkingMemoryPoint]
    ) -> None:
        assert snapshot_id == "snapshot-1"
        assert points


class FakePool:
    def __init__(self) -> None:
        self.query = ""
        self.args: tuple[object, ...] = ()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.query = query
        self.args = args
        return {"snapshot_id": UUID("00000000-0000-0000-0000-000000000999")}

    async def fetch(self, query: str, *args: object) -> list[object]:
        return []

    async def execute(self, query: str, *args: object) -> str:
        return "INSERT 0 1"


def test_snapshot_checksum_is_stable_and_ignores_order() -> None:
    left = compute_snapshot_checksum([_point("b"), _point("a")])
    right = compute_snapshot_checksum([_point("a"), _point("b")])

    assert left == right
    assert len(left) == 64


async def test_snapshot_service_filters_expired_points_and_epoch_is_monotonic() -> None:
    service = SnapshotService(store=None, repository=None)
    points = [_point("a"), _point("expired", expired=True)]

    active = service.active_points(points, now=NOW)
    epoch1 = service.next_snapshot_epoch("agent", str(uuid4()))
    epoch2 = service.next_snapshot_epoch("agent", str(uuid4()))

    assert [point.point_id for point in active] == ["a"]
    assert epoch2 > epoch1
    assert epoch1 > 1_700_000_000_000


def test_snapshot_epoch_uses_wall_clock_milliseconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.working_memory.snapshot_service.time.time_ns",
        lambda: 1_800_000_000_000_000_000,
    )
    monkeypatch.setattr(snapshot_service, "_LAST_EPOCH_MS", 0)

    first = snapshot_service.next_snapshot_epoch_ms()
    second = snapshot_service.next_snapshot_epoch_ms()

    assert first == 1_800_000_000_000
    assert second == 1_800_000_000_001


async def test_create_session_snapshot_lets_repository_allocate_epoch() -> None:
    created_at = datetime.now(UTC)
    point = WorkingMemoryPoint(
        point_id="a",
        agent_id="agent",
        session_id=SESSION_ID,
        memory_kind="turn_summary",
        vector=(0.1, 0.2),
        vector_dim=2,
        importance=0.5,
        recency_ts=created_at,
        created_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(seconds=60),
        ttl_seconds=60,
        embedding_model="nomic",
    )
    store = FakeStore([point])
    repository = FakeRepository()
    service = SnapshotService(store=store, repository=repository)

    result = await service.create_session_snapshot(
        agent_id=point.agent_id, session_id=str(point.session_id)
    )

    assert result["snapshot_id"] == "snapshot-1"
    assert repository.header_kwargs is not None
    assert repository.header_kwargs["snapshot_epoch"] is None
    assert store.checkpointed == (["a"], "snapshot-1")


async def test_create_delta_snapshot_requires_checkpoint_id() -> None:
    service = SnapshotService(store=None, repository=None)

    with pytest.raises(ValueError, match="since_checkpoint_id is required"):
        await service.create_delta_snapshot(
            agent_id="agent",
            session_id=str(SESSION_ID),
            since_checkpoint_id=" ",
        )


async def test_checkpoint_repository_allocates_epoch_with_db_lock() -> None:
    pool = FakePool()
    repository = WorkingMemoryCheckpointRepository(pool)

    await repository.create_snapshot_header(
        agent_id="agent",
        session_id=str(SESSION_ID),
        snapshot_epoch=None,
        collection_name="quimera_working_memory",
        vector_name="working_memory",
        embedding_model="nomic",
        vector_dim=768,
        snapshot_kind="full",
        point_count=0,
        checksum="abc",
    )

    assert "pg_advisory_xact_lock" in pool.query
    assert "COALESCE(MAX(snapshot_epoch), 0) + 1" in pool.query
    assert pool.args[2] is None


def test_should_snapshot_policy() -> None:
    service = SnapshotService(store=None, repository=None)

    assert service.should_snapshot(write_count=20, elapsed_seconds=1)
    assert service.should_snapshot(write_count=1, elapsed_seconds=300)
    assert not service.should_snapshot(write_count=1, elapsed_seconds=1)
