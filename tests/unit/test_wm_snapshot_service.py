from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.snapshot_service import SnapshotService, compute_snapshot_checksum


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
        expires_at=NOW - timedelta(seconds=1) if expired else NOW + timedelta(seconds=60),
        ttl_seconds=60,
        embedding_model="nomic",
    )


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


def test_should_snapshot_policy() -> None:
    service = SnapshotService(store=None, repository=None)

    assert service.should_snapshot(write_count=20, elapsed_seconds=1)
    assert service.should_snapshot(write_count=1, elapsed_seconds=300)
    assert not service.should_snapshot(write_count=1, elapsed_seconds=1)
