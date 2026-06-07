from __future__ import annotations

from backend.working_memory.cleanup import CleanupService
from backend.working_memory.config import WorkingMemorySettings


class FakeStore:
    def __init__(self) -> None:
        self.called = False

    async def delete_expired_points(self, *, agent_id: str | None = None, session_id: str | None = None) -> int:
        self.called = True
        return 3


async def test_cleanup_disabled_by_default() -> None:
    store = FakeStore()
    service = CleanupService(store=store, settings=WorkingMemorySettings(cleanup_enabled=False))

    result = await service.cleanup_expired()

    assert result.status == "disabled"
    assert result.deleted_count == 0
    assert store.called is False


async def test_cleanup_only_allows_working_memory_collections() -> None:
    store = FakeStore()
    service = CleanupService(
        store=store,
        settings=WorkingMemorySettings(collection_name="quimera_working_memory_test_cleanup", cleanup_enabled=True),
    )

    result = await service.cleanup_expired(agent_id="agent")

    assert result.status == "ok"
    assert result.deleted_count == 3
    assert store.called is True
