from __future__ import annotations

from contextvars import ContextVar

from backend.observability.attributes import (
    QUIMERA_AGENT_ID,
    QUIMERA_PROFILE_NAME,
    QUIMERA_SESSION_ID,
    QUIMERA_TASK_ID,
)
from backend.observability.safety import validate_attributes

_agent_id: ContextVar[str | None] = ContextVar("quimera_agent_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("quimera_session_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("quimera_task_id", default=None)
_profile_name: ContextVar[str | None] = ContextVar("quimera_profile_name", default=None)


def set_quimera_context(
    *,
    agent_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    profile_name: str | None = None,
) -> dict[str, str]:
    if agent_id is not None:
        _agent_id.set(agent_id)
    if session_id is not None:
        _session_id.set(session_id)
    if task_id is not None:
        _task_id.set(task_id)
    if profile_name is not None:
        _profile_name.set(profile_name)
    return get_quimera_context_attributes()


def clear_quimera_context() -> None:
    _agent_id.set(None)
    _session_id.set(None)
    _task_id.set(None)
    _profile_name.set(None)


def get_quimera_context_attributes() -> dict[str, str]:
    attrs = {
        QUIMERA_AGENT_ID: _agent_id.get(),
        QUIMERA_SESSION_ID: _session_id.get(),
        QUIMERA_TASK_ID: _task_id.get(),
        QUIMERA_PROFILE_NAME: _profile_name.get(),
    }
    compact = {key: value for key, value in attrs.items() if value is not None}
    return {key: str(value) for key, value in validate_attributes(compact).items()}
