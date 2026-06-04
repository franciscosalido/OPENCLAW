from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Awaitable
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.memory.postgres.models import AgentState, Turn
from backend.memory.postgres.repository import PostgresMemoryRepository

pytestmark = pytest.mark.integration


def _dsn() -> str | None:
    return os.getenv("TEST_POSTGRES_DSN") or os.getenv("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def repository() -> AsyncGenerator[PostgresMemoryRepository, None]:
    dsn = _dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    client = await PostgresClient.create(dsn=dsn)
    await run_migrations(client)
    try:
        yield PostgresMemoryRepository(client)
    finally:
        await client.close()


async def test_concurrent_agent_state_upsert_same_key_real(repository: PostgresMemoryRepository) -> None:
    agent_id = f"agent-{uuid4().hex}"
    session = await repository.create_session(agent_id=agent_id)
    state_tasks: list[Awaitable[AgentState]] = [
        repository.upsert_agent_state(agent_id, session.session_id, "plan", {"v": i})
        for i in range(10)
    ]

    results = await asyncio.gather(*state_tasks)

    assert len({result.state_id for result in results}) == 1


async def test_concurrent_turn_append_real(repository: PostgresMemoryRepository) -> None:
    session = await repository.create_session(agent_id=f"agent-{uuid4().hex}")
    turn_tasks: list[Awaitable[Turn]] = [
        repository.append_turn(session.session_id, "user", f"msg {i}")
        for i in range(50)
    ]

    turns = await asyncio.gather(*turn_tasks)

    assert len({turn.turn_id for turn in turns}) == 50
