"""Cleanup helpers for expired working-memory points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.observability.decorators import traced_cache
from backend.working_memory.config import WorkingMemorySettings


@dataclass(frozen=True, slots=True)
class CleanupResult:
    status: str
    deleted_count: int


class CleanupStore(Protocol):
    async def delete_expired_points(self, *, agent_id: str | None = None, session_id: str | None = None) -> int:
        ...


class CleanupService:
    def __init__(self, *, store: CleanupStore, settings: WorkingMemorySettings) -> None:
        self._store = store
        self._settings = settings

    @traced_cache(operation="working_memory.cleanup", collection="quimera_working_memory")
    async def cleanup_expired(self, *, agent_id: str | None = None, session_id: str | None = None) -> CleanupResult:
        if not self._settings.cleanup_enabled:
            return CleanupResult(status="disabled", deleted_count=0)
        _assert_cleanup_collection(self._settings.collection_name)
        deleted = await self._store.delete_expired_points(agent_id=agent_id, session_id=session_id)
        return CleanupResult(status="ok", deleted_count=deleted)


def _assert_cleanup_collection(collection_name: str) -> None:
    if collection_name == "quimera_working_memory" or collection_name.startswith("quimera_working_memory_test_"):
        return
    raise ValueError("cleanup is only allowed for working memory collections")
