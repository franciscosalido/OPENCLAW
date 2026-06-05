"""Safety scans for PR-08 integration artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

FORBIDDEN_FIELD_PARTS: frozenset[str] = frozenset(
    {
        "prompt",
        "raw_prompt",
        "answer",
        "response",
        "chunk_text",
        "document_text",
        "vector",
        "embedding",
        "payload",
        "authorization",
        "api_key",
        "secret",
        "password",
        "dsn",
        "connection_string",
    }
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
ALLOWED_AUDIT_FLAG_KEYS = frozenset({"vectors_seen", "raw_chunks_seen", "secrets_seen", "forbidden_fields_seen"})


def find_forbidden_fields(value: object) -> list[str]:
    found: set[str] = set()
    _walk(value, found)
    return sorted(found)


def assert_no_forbidden_fields(value: object) -> None:
    found = find_forbidden_fields(value)
    if found:
        raise ValueError(f"forbidden fields present: {', '.join(found)}")


def is_safe_trace_id(value: str) -> bool:
    return bool(SAFE_ID_RE.fullmatch(value))


def json_has_no_forbidden_fields(value: Mapping[str, Any]) -> bool:
    encoded = json.dumps(value, sort_keys=True)
    lowered = encoded.lower()
    return not any(part in lowered for part in FORBIDDEN_FIELD_PARTS)


def _walk(value: object, found: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text not in ALLOWED_AUDIT_FLAG_KEYS:
                for part in FORBIDDEN_FIELD_PARTS:
                    if part in key_text:
                        found.add(str(key))
            _walk(item, found)
    elif isinstance(value, list | tuple):
        for item in value:
            _walk(item, found)
