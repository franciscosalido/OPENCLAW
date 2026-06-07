"""Safety gates for hot working memory payloads."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID


FORBIDDEN_WORKING_MEMORY_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "answer",
        "response",
        "completion",
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
        "embedding",
    }
)
SAFE_OPERATIONAL_KEYS = frozenset(
    {
        "embedding_model",
        "vector_dim",
        "source_ref",
        "safe_summary",
        "payload_checksum",
        "point_id",
        "agent_id",
        "session_id",
        "task_id",
        "topic",
        "memory_kind",
        "importance",
        "recency_ts",
        "created_at",
        "updated_at",
        "expires_at",
        "ttl_seconds",
        "checkpoint_id",
        "schema_version",
        "metadata",
        "checksum",
        "points",
        "count",
    }
)
_SECRET_PATTERN = re.compile(
    r"(authorization\s*:|bearer\s+[a-z0-9._-]+|sk-[a-z0-9_-]+|api[_-]?key|password|secret|postgresql://)",
    re.IGNORECASE,
)


class WorkingMemorySafetyError(ValueError):
    """Raised when working-memory data is unsafe to persist or report."""


def validate_safe_payload(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return mapping as a dict after rejecting unsafe keys recursively."""

    _reject_sensitive_keys(mapping)
    return dict(mapping)


def sanitize_metadata(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return metadata with sensitive nested keys redacted, not persisted raw."""

    if mapping is None:
        return {}
    return {str(key): _sanitize_value(str(key), value) for key, value in mapping.items()}


def validate_safe_summary(text: str | None) -> str | None:
    """Validate an optional short summary safe enough for MCP/tool output."""

    if text is None:
        return None
    clean = text.strip()
    if len(clean) > 512:
        raise WorkingMemorySafetyError("safe_summary must be <= 512 characters")
    if _SECRET_PATTERN.search(clean):
        raise WorkingMemorySafetyError("safe_summary must not contain secret-like text")
    return clean


def compute_payload_checksum(mapping: Mapping[str, Any]) -> str:
    """Return deterministic SHA-256 checksum for safe payload metadata."""

    safe = validate_safe_payload(sanitize_metadata(mapping))
    encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def assert_agent_session_scope(agent_id: str, session_id: str) -> None:
    """Validate mandatory agent/session scope."""

    if not agent_id.strip():
        raise WorkingMemorySafetyError("agent_id cannot be empty")
    try:
        UUID(session_id)
    except ValueError as exc:
        raise WorkingMemorySafetyError("session_id must be a valid UUID") from exc


def _reject_sensitive_keys(mapping: Mapping[str, Any]) -> None:
    for key, value in mapping.items():
        lowered = str(key).casefold()
        if _is_sensitive_key(lowered):
            raise WorkingMemorySafetyError(f"sensitive working-memory key is forbidden: {key}")
        if isinstance(value, Mapping):
            _reject_sensitive_keys(value)


def _sanitize_value(key: str, value: Any) -> Any:
    lowered = key.casefold()
    if _is_sensitive_key(lowered):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(child_key): _sanitize_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    if isinstance(value, str) and _SECRET_PATTERN.search(value):
        return "[REDACTED]"
    return value


def _is_sensitive_key(lowered_key: str) -> bool:
    if lowered_key in SAFE_OPERATIONAL_KEYS:
        return False
    if lowered_key in FORBIDDEN_WORKING_MEMORY_KEYS:
        return True
    return any(token in lowered_key for token in FORBIDDEN_WORKING_MEMORY_KEYS - {"vector", "embedding", "payload"})
