from __future__ import annotations

import asyncio

from backend.observability.context import (
    clear_quimera_context,
    get_quimera_context_attributes,
    set_quimera_context,
)


def test_quimera_context_roundtrip_and_clear() -> None:
    clear_quimera_context()

    set_quimera_context(agent_id="agent-a", session_id="session-a", task_id="task-a")

    assert get_quimera_context_attributes() == {
        "quimera.agent_id": "agent-a",
        "quimera.session_id": "session-a",
        "quimera.task_id": "task-a",
    }
    clear_quimera_context()
    assert get_quimera_context_attributes() == {}


async def test_contextvars_do_not_leak_between_gather_tasks() -> None:
    clear_quimera_context()

    async def worker(session_id: str) -> str:
        set_quimera_context(session_id=session_id)
        await asyncio.sleep(0)
        return get_quimera_context_attributes()["quimera.session_id"]

    assert list(await asyncio.gather(worker("a"), worker("b"))) == ["a", "b"]
