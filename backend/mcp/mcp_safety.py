from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import UUID

SENSITIVE_KEYS = frozenset(
    {
        "prompt",
        "answer",
        "response",
        "chunks",
        "chunk",
        "chunk_text",
        "document_text",
        "vector",
        "embedding",
        "secret",
        "api_key",
        "token",
        "password",
        "dsn",
        "connection_string",
    }
)
_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class McpSafetyError(ValueError):
    pass


def validate_uuid(value: str, field_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise McpSafetyError(f"{field_name} must be a valid UUID") from exc


def validate_limit(value: int, *, minimum: int = 1, maximum: int = 100) -> int:
    if minimum <= value <= maximum:
        return value
    raise McpSafetyError(f"limit must be between {minimum} and {maximum}")


def block_sensitive_keys(mapping: Mapping[str, object]) -> None:
    for key, value in mapping.items():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or any(part in lowered for part in SENSITIVE_KEYS):
            raise McpSafetyError(f"sensitive key is forbidden: {key}")
        if isinstance(value, Mapping):
            block_sensitive_keys(value)


def validate_safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    block_sensitive_keys(value)
    return dict(value)


def validate_non_empty_text(value: str, field_name: str) -> str:
    clean = value.strip()
    if not clean:
        raise McpSafetyError(f"{field_name} cannot be empty")
    return clean


def validate_collection_name(name: str) -> str:
    clean = validate_non_empty_text(name, "collection_name")
    if not _COLLECTION_RE.fullmatch(clean) or ".." in clean or "/" in clean or "\\" in clean:
        raise McpSafetyError("collection_name must be a safe collection identifier")
    allowed = {"quimera_knowledge", "quimera_query_cache", "quimera_llm_cache"}
    if clean not in allowed and not clean.startswith("quimera_"):
        raise McpSafetyError("collection_name is not allowed for Quimera MCP")
    return clean


def sanitize_error(exc: BaseException) -> str:
    text = str(exc)
    for marker in ("password=", "api_key=", "token=", "secret=", "postgresql://"):
        if marker in text.lower():
            return "[REDACTED]"
    return text[:240]

