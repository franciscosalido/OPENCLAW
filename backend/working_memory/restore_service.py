"""Restore working-memory Qdrant points from pgvector checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.observability.decorators import traced_cache
from backend.working_memory.models import WorkingMemoryPoint


class RestoreStore(Protocol):
    async def restore_points_from_snapshot(self, points: list[WorkingMemoryPoint]) -> int: ...
    async def delete_session_points(self, *, agent_id: str, session_id: str) -> int: ...


class RestoreRepository(Protocol):
    async def get_latest_snapshot(self, *, agent_id: str, session_id: str) -> dict[str, Any] | None: ...
    async def load_snapshot_points(self, snapshot_id: str) -> list[WorkingMemoryPoint]: ...
    async def validate_snapshot_checksum(self, snapshot_id: str) -> bool: ...
    async def mark_snapshot_restored(self, snapshot_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RestoreReport:
    status: str
    snapshot_id: str | None
    restored_count: int
    skipped_expired_count: int
    checksum_ok: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "restored_count": self.restored_count,
            "skipped_expired_count": self.skipped_expired_count,
            "checksum_ok": self.checksum_ok,
            "warnings": list(self.warnings),
        }


class RestoreService:
    """Merge or gated-replace restore service."""

    def __init__(
        self,
        *,
        store: RestoreStore,
        repository: RestoreRepository,
        replace_enabled: bool = False,
        abort_on_checksum_fail: bool = False,
    ) -> None:
        self._store = store
        self._repository = repository
        self._replace_enabled = replace_enabled
        self._abort_on_checksum_fail = abort_on_checksum_fail

    async def restore_latest_snapshot(self, *, agent_id: str, session_id: str) -> RestoreReport:
        snapshot = await self._repository.get_latest_snapshot(agent_id=agent_id, session_id=session_id)
        if snapshot is None:
            return RestoreReport(status="skipped", snapshot_id=None, restored_count=0, skipped_expired_count=0, checksum_ok=False, warnings=["snapshot not found"])
        return await self.restore_snapshot(str(snapshot["snapshot_id"]), agent_id=agent_id, session_id=session_id)

    @traced_cache(operation="working_memory.restore", collection="quimera_working_memory")
    async def restore_snapshot(self, snapshot_id: str, *, agent_id: str, session_id: str, replace: bool = False) -> RestoreReport:
        if replace and not self._replace_enabled:
            raise ValueError("working memory replace restore is disabled")
        checksum_ok = await self._repository.validate_snapshot_checksum(snapshot_id)
        if not checksum_ok and self._abort_on_checksum_fail:
            return RestoreReport(
                status="fail",
                snapshot_id=snapshot_id,
                restored_count=0,
                skipped_expired_count=0,
                checksum_ok=False,
                warnings=["snapshot checksum mismatch; restore aborted"],
            )
        points = await self._repository.load_snapshot_points(snapshot_id)
        now = datetime.now(UTC)
        active = [point for point in points if not point.is_expired(now)]
        skipped = len(points) - len(active)
        if replace:
            await self._store.delete_session_points(agent_id=agent_id, session_id=session_id)
        restored_count = await self._store.restore_points_from_snapshot(active)
        await self._repository.mark_snapshot_restored(snapshot_id)
        return RestoreReport(
            status="ok" if checksum_ok else "warn",
            snapshot_id=snapshot_id,
            restored_count=restored_count,
            skipped_expired_count=skipped,
            checksum_ok=checksum_ok,
            warnings=[] if checksum_ok else ["snapshot checksum mismatch"],
        )

    async def dry_run_restore(self, snapshot_id: str) -> RestoreReport:
        points = await self._repository.load_snapshot_points(snapshot_id)
        checksum_ok = await self._repository.validate_snapshot_checksum(snapshot_id)
        return RestoreReport(status="dry_run", snapshot_id=snapshot_id, restored_count=len(points), skipped_expired_count=0, checksum_ok=checksum_ok)

    async def verify_restored_count(self, snapshot_id: str) -> int:
        return len(await self._repository.load_snapshot_points(snapshot_id))

    async def verify_restored_checksum(self, snapshot_id: str) -> bool:
        return await self._repository.validate_snapshot_checksum(snapshot_id)
