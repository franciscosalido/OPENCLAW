from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.memory.postgres.models import AgentState, EntityMention, Session, Turn


def _now() -> datetime:
    return datetime.now(UTC)


def test_session_model_is_immutable() -> None:
    session = Session(
        session_id=uuid4(),
        agent_id="agent-1",
        user_id=None,
        created_at=_now(),
        updated_at=_now(),
        metadata={},
    )

    with pytest.raises((AttributeError, FrozenInstanceError)):
        session.agent_id = "other"  # type: ignore[misc]


def test_turn_accepts_valid_roles() -> None:
    for role in ("user", "assistant", "system", "tool"):
        turn = Turn(
            turn_id=uuid4(),
            session_id=uuid4(),
            role=role,
            content="safe synthetic content",
            created_at=_now(),
            token_count=None,
            latency_ms=None,
        )
        assert turn.role == role


def test_turn_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="role"):
        Turn(
            turn_id=uuid4(),
            session_id=uuid4(),
            role="supervisor",  # type: ignore[arg-type]
            content="safe synthetic content",
            created_at=_now(),
            token_count=None,
            latency_ms=None,
        )


def test_turn_rejects_negative_token_count() -> None:
    with pytest.raises(ValueError, match="token_count"):
        Turn(
            turn_id=uuid4(),
            session_id=uuid4(),
            role="user",
            content="safe synthetic content",
            created_at=_now(),
            token_count=-1,
            latency_ms=None,
        )


def test_turn_rejects_negative_latency() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        Turn(
            turn_id=uuid4(),
            session_id=uuid4(),
            role="assistant",
            content="safe synthetic content",
            created_at=_now(),
            token_count=None,
            latency_ms=-0.1,
        )


def test_agent_state_schema_version_present() -> None:
    state = AgentState(
        state_id=uuid4(),
        agent_id="agent-1",
        session_id=uuid4(),
        state_key="working_memory",
        state_value={"step": "synthetic"},
        schema_version="agent-state-v1",
        updated_at=_now(),
    )

    assert state.schema_version == "agent-state-v1"


def test_agent_state_rejects_empty_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        AgentState(
            state_id=uuid4(),
            agent_id="agent-1",
            session_id=uuid4(),
            state_key="working_memory",
            state_value={},
            schema_version=" ",
            updated_at=_now(),
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_entity_mention_rejects_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    with pytest.raises(ValueError, match="confidence"):
        EntityMention(
            mention_id=uuid4(),
            turn_id=uuid4(),
            entity_text="OpenClaw",
            entity_type="ORG",
            start_char=0,
            end_char=8,
            confidence=confidence,
        )


def test_entity_mention_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="end_char"):
        EntityMention(
            mention_id=uuid4(),
            turn_id=uuid4(),
            entity_text="OpenClaw",
            entity_type="ORG",
            start_char=9,
            end_char=8,
            confidence=None,
        )


def test_models_reject_naive_datetimes() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        Session(
            session_id=uuid4(),
            agent_id="agent-1",
            user_id=None,
            created_at=naive,
            updated_at=_now(),
            metadata={},
        )


def test_required_strings_reject_blank_values() -> None:
    with pytest.raises(ValueError, match="agent_id"):
        Session(
            session_id=uuid4(),
            agent_id=" ",
            user_id=None,
            created_at=_now(),
            updated_at=_now(),
            metadata={},
        )
