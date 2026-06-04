from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.memory.postgres.repository import PostgresMemoryRepository


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def repo_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    client = await PostgresClient.create(dsn=dsn)
    await run_migrations(client)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def repository(repo_client: PostgresClient) -> PostgresMemoryRepository:
    return PostgresMemoryRepository(repo_client)


async def test_healthcheck_select_1(repo_client: PostgresClient) -> None:
    assert await repo_client.healthcheck() is True


async def test_create_and_get_session_roundtrip(
    repository: PostgresMemoryRepository,
) -> None:
    agent_id = f"test-agent-{uuid4().hex}"
    session = await repository.create_session(
        agent_id=agent_id,
        metadata={"unicode": "acao sintetica"},
    )
    fetched = await repository.get_session(session.session_id)

    assert fetched is not None
    assert fetched.agent_id == agent_id
    assert fetched.metadata == {"unicode": "acao sintetica"}


async def test_append_turn_and_get_recent_turns(
    repository: PostgresMemoryRepository,
) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")
    first = await repository.append_turn(session.session_id, "user", "ola")
    second = await repository.append_turn(session.session_id, "assistant", "resposta")
    turns = await repository.get_recent_turns(session.session_id, limit=20)

    assert [turn.turn_id for turn in turns] == [first.turn_id, second.turn_id]


async def test_turn_invalid_role_rejected_by_database(
    repo_client: PostgresClient,
    repository: PostgresMemoryRepository,
) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")

    with pytest.raises(Exception):
        await repo_client.pool.execute(
            "INSERT INTO turns(session_id, role, content) VALUES($1, $2, $3)",
            session.session_id,
            "supervisor",
            "safe synthetic content",
        )


async def test_upsert_agent_state_insert_then_update(
    repository: PostgresMemoryRepository,
) -> None:
    agent_id = f"test-agent-{uuid4().hex}"
    session = await repository.create_session(agent_id=agent_id)
    first = await repository.upsert_agent_state(
        agent_id,
        session.session_id,
        "working_memory",
        {"step": 1},
    )
    second = await repository.upsert_agent_state(
        agent_id,
        session.session_id,
        "working_memory",
        {"step": 2},
    )

    assert first.state_id == second.state_id
    assert second.state_value == {"step": 2}


async def test_record_entity_mention_roundtrip(
    repository: PostgresMemoryRepository,
) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")
    turn = await repository.append_turn(session.session_id, "user", "OpenClaw local")
    mention = await repository.record_entity_mention(
        turn.turn_id,
        "OpenClaw",
        "ORG",
        0,
        8,
        confidence=0.9,
    )
    mentions = await repository.get_entity_mentions_for_turn(turn.turn_id)

    assert [item.mention_id for item in mentions] == [mention.mention_id]


async def test_delete_session_cascades_turns_and_states(
    repo_client: PostgresClient,
    repository: PostgresMemoryRepository,
) -> None:
    agent_id = f"test-agent-{uuid4().hex}"
    session = await repository.create_session(agent_id=agent_id)
    turn = await repository.append_turn(session.session_id, "user", "ola")
    await repository.upsert_agent_state(agent_id, session.session_id, "plan", {"ok": True})
    await repo_client.pool.execute(
        "DELETE FROM sessions WHERE session_id = $1", session.session_id
    )
    turn_count = await repo_client.pool.fetchval(
        "SELECT count(*) FROM turns WHERE turn_id = $1", turn.turn_id
    )
    state_count = await repo_client.pool.fetchval(
        "SELECT count(*) FROM agent_states WHERE session_id = $1", session.session_id
    )

    assert turn_count == 0
    assert state_count == 0


async def test_delete_turn_cascades_entity_mentions(
    repo_client: PostgresClient,
    repository: PostgresMemoryRepository,
) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")
    turn = await repository.append_turn(session.session_id, "user", "OpenClaw")
    mention = await repository.record_entity_mention(
        turn.turn_id, "OpenClaw", "ORG", 0, 8
    )
    await repo_client.pool.execute("DELETE FROM turns WHERE turn_id = $1", turn.turn_id)
    count = await repo_client.pool.fetchval(
        "SELECT count(*) FROM entity_mentions WHERE mention_id = $1",
        mention.mention_id,
    )

    assert count == 0


async def test_concurrent_agent_state_upsert_same_key_is_safe(
    repository: PostgresMemoryRepository,
) -> None:
    import asyncio

    agent_id = f"test-agent-{uuid4().hex}"
    session = await repository.create_session(agent_id=agent_id)

    results = await asyncio.gather(
        repository.upsert_agent_state(agent_id, session.session_id, "plan", {"v": 1}),
        repository.upsert_agent_state(agent_id, session.session_id, "plan", {"v": 2}),
    )

    assert results[0].state_id == results[1].state_id


async def test_unicode_content_roundtrip(repository: PostgresMemoryRepository) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")
    turn = await repository.append_turn(session.session_id, "user", "olá ação 測試")
    turns = await repository.get_recent_turns(session.session_id)

    assert turns[0].content == turn.content


async def test_jsonb_metadata_roundtrip(repository: PostgresMemoryRepository) -> None:
    session = await repository.create_session(
        agent_id=f"test-agent-{uuid4().hex}",
        metadata={"nested": {"value": 1}, "items": ["a", "b"]},
    )
    fetched = await repository.get_session(session.session_id)

    assert fetched is not None
    assert fetched.metadata == {"nested": {"value": 1}, "items": ["a", "b"]}


async def test_sql_injection_payload_is_stored_not_executed(
    repo_client: PostgresClient,
    repository: PostgresMemoryRepository,
) -> None:
    session = await repository.create_session(agent_id=f"test-agent-{uuid4().hex}")
    payload = "Robert'); DROP TABLE sessions;--"
    turn = await repository.append_turn(session.session_id, "user", payload)
    fetched = await repository.get_recent_turns(session.session_id)
    table_exists = await repo_client.pool.fetchval("SELECT to_regclass('public.sessions')")

    assert fetched[0].content == turn.content
    assert table_exists == "sessions"
