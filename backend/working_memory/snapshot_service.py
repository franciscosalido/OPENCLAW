"""Snapshot orchestration for working memory."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import time
from typing import Any, Protocol

from backend.observability.decorators import traced_cache
from backend.working_memory.config import WorkingMemorySettings
from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.safety import compute_payload_checksum


class SnapshotStore(Protocol):
    async def export_session_points_for_snapshot(
        self, *, agent_id: str, session_id: str, limit: int | None = None
    ) -> list[WorkingMemoryPoint]: ...
    async def mark_checkpointed(
        self, *, point_ids: Iterable[str], checkpoint_id: str
    ) -> None: ...


class SnapshotRepository(Protocol):
    async def create_snapshot_header(self, **kwargs: Any) -> str: ...
    async def insert_snapshot_points(
        self, *, snapshot_id: str, points: list[WorkingMemoryPoint]
    ) -> None: ...


_LAST_EPOCH_MS = 0


class SnapshotService:
    """Create full or delta snapshots on demand; no daemon."""

    def __init__(
        self,
        *,
        store: SnapshotStore | None,
        repository: SnapshotRepository | None,
        settings: WorkingMemorySettings | None = None,
    ) -> None:
        self._store = store
        self._repository = repository
        self._settings = settings or WorkingMemorySettings()

    @traced_cache(
        operation="working_memory.snapshot", collection="quimera_working_memory"
    )
    async def create_session_snapshot(
        self, *, agent_id: str, session_id: str, kind: str = "full"
    ) -> dict[str, Any]:
        if self._store is None or self._repository is None:
            raise RuntimeError("snapshot dependencies are not configured")
        points = self.active_points(
            await self._store.export_session_points_for_snapshot(
                agent_id=agent_id, session_id=session_id
            ),
            now=datetime.now(UTC),
        )
        checksum = compute_snapshot_checksum(points)
        snapshot_id = await self._repository.create_snapshot_header(
            agent_id=agent_id,
            session_id=session_id,
            snapshot_epoch=None,
            collection_name=self._settings.collection_name,
            vector_name=self._settings.vector_name,
            embedding_model=points[0].embedding_model if points else "unknown",
            vector_dim=points[0].vector_dim if points else self._settings.vector_size,
            snapshot_kind=kind,
            point_count=len(points),
            checksum=checksum,
            metadata={"kind": kind},
        )
        await self._repository.insert_snapshot_points(
            snapshot_id=snapshot_id, points=points
        )
        await self._store.mark_checkpointed(
            point_ids=[point.point_id for point in points], checkpoint_id=snapshot_id
        )
        return {
            "snapshot_id": snapshot_id,
            "point_count": len(points),
            "checksum": checksum,
        }

    async def create_delta_snapshot(
        self, *, agent_id: str, session_id: str, since_checkpoint_id: str
    ) -> dict[str, Any]:
        if not since_checkpoint_id.strip():
            raise ValueError("since_checkpoint_id is required")
        return await self.create_session_snapshot(
            agent_id=agent_id, session_id=session_id, kind="delta"
        )

    def active_points(
        self, points: Iterable[WorkingMemoryPoint], *, now: datetime
    ) -> list[WorkingMemoryPoint]:
        return [point for point in points if not point.is_expired(now)]

    def next_snapshot_epoch(self, agent_id: str, session_id: str) -> int:
        if not agent_id.strip() or not session_id.strip():
            raise ValueError("agent_id and session_id are required")
        return next_snapshot_epoch_ms()

    def should_snapshot(self, *, write_count: int, elapsed_seconds: int) -> bool:
        return (
            write_count >= self._settings.snapshot_every_writes
            or elapsed_seconds >= self._settings.snapshot_interval_seconds
        )


def compute_snapshot_checksum(points: Iterable[WorkingMemoryPoint]) -> str:
    rows = [
        {"point_id": point.point_id, "payload_checksum": point.payload_checksum}
        for point in sorted(points, key=lambda item: item.point_id)
    ]
    return compute_payload_checksum({"points": rows})


def next_snapshot_epoch_ms() -> int:
    """Return a wall-clock millisecond epoch with a per-process monotonic guard."""

    global _LAST_EPOCH_MS
    current = time.time_ns() // 1_000_000
    if current <= _LAST_EPOCH_MS:
        current = _LAST_EPOCH_MS + 1
    _LAST_EPOCH_MS = current
    return current
