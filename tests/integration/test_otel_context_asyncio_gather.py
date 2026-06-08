from __future__ import annotations

import asyncio

import pytest

from backend.observability.context import (
    clear_quimera_context,
    get_quimera_context_attributes,
    set_quimera_context,
)

pytestmark = pytest.mark.integration


async def test_otel_context_asyncio_gather_isolated() -> None:
    clear_quimera_context()

    async def worker(task_id: str) -> str:
        set_quimera_context(task_id=task_id)
        await asyncio.sleep(0)
        return get_quimera_context_attributes()["quimera.task_id"]

    assert list(await asyncio.gather(worker("task-a"), worker("task-b"))) == [
        "task-a",
        "task-b",
    ]
