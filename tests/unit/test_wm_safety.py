from __future__ import annotations

import pytest

from backend.working_memory.safety import (
    WorkingMemorySafetyError,
    assert_agent_session_scope,
    compute_payload_checksum,
    sanitize_metadata,
    validate_safe_payload,
    validate_safe_summary,
)


@pytest.mark.parametrize(
    "key",
    [
        "prompt",
        "raw_prompt",
        "answer",
        "response",
        "chunk",
        "chunk_text",
        "document_text",
        "payload",
        "authorization",
        "api_key",
        "token",
        "password",
        "secret",
        "dsn",
        "connection_string",
        "vector",
    ],
)
def test_validate_safe_payload_rejects_sensitive_keys(key: str) -> None:
    with pytest.raises(WorkingMemorySafetyError, match="sensitive"):
        validate_safe_payload({key: "bad"})


def test_sanitize_metadata_redacts_nested_sensitive_values() -> None:
    sanitized = sanitize_metadata({"safe": "yes", "nested": {"token": "bad", "ok": 1}})

    assert sanitized == {"safe": "yes", "nested": {"token": "[REDACTED]", "ok": 1}}


def test_safe_summary_limit_and_secret_patterns() -> None:
    assert validate_safe_summary("a safe summary") == "a safe summary"
    with pytest.raises(WorkingMemorySafetyError, match="512"):
        validate_safe_summary("x" * 513)
    with pytest.raises(WorkingMemorySafetyError, match="secret"):
        validate_safe_summary("Authorization: Bearer abc")


def test_checksum_is_deterministic_and_order_insensitive() -> None:
    left = compute_payload_checksum({"b": 2, "a": 1})
    right = compute_payload_checksum({"a": 1, "b": 2})

    assert left == right
    assert len(left) == 64


def test_agent_session_scope_validation() -> None:
    assert_agent_session_scope("agent", "00000000-0000-0000-0000-000000000001")
    with pytest.raises(WorkingMemorySafetyError):
        assert_agent_session_scope(" ", "00000000-0000-0000-0000-000000000001")
    with pytest.raises(WorkingMemorySafetyError):
        assert_agent_session_scope("agent", "not-a-uuid")
