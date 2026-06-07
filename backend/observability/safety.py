from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypeAlias

from backend.observability.attributes import (
    PII_FORBIDDEN_ATTRS,
    PII_FORBIDDEN_SUBSTRINGS,
    SAFE_ATTRS,
    SAFE_ATTRIBUTE_PREFIXES,
)

AttributeValue: TypeAlias = str | bool | int | float

_ATTR_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._-]+|(?<![a-z0-9])sk-[a-z0-9_-]+|password=|api[_-]?key=|token=|secret=|postgres(?:ql)?://[^@\s]+@)"
)


def _is_forbidden_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in PII_FORBIDDEN_ATTRS:
        return True
    if normalized in SAFE_ATTRS:
        return False
    return any(part in normalized for part in PII_FORBIDDEN_SUBSTRINGS)


def validate_attribute_key(key: str) -> str:
    normalized = key.strip()
    if not normalized:
        raise ValueError("attribute key cannot be empty")
    if normalized != normalized.lower():
        raise ValueError(f"attribute key must be lowercase: {key}")
    if not _ATTR_KEY_RE.match(normalized):
        raise ValueError(f"attribute key must be dotted lowercase tokens: {key}")
    if _is_forbidden_key(normalized):
        raise ValueError(f"attribute key is not safe for telemetry: {key}")
    if normalized not in SAFE_ATTRS and not normalized.startswith(
        tuple(SAFE_ATTRIBUTE_PREFIXES)
    ):
        raise ValueError(f"attribute key prefix is not allowed: {key}")
    return normalized


def validate_attribute_value(value: object) -> AttributeValue:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if _SECRET_VALUE_RE.search(value):
            raise ValueError("attribute value appears to contain a secret")
        return value
    raise ValueError("attribute value must be a primitive")


def validate_attributes(
    attributes: Mapping[str, object] | None,
) -> dict[str, AttributeValue]:
    if attributes is None:
        return {}
    validated: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        validated[validate_attribute_key(key)] = validate_attribute_value(value)
    return validated


def sanitize_error_message(message: str) -> str:
    sanitized = _SECRET_VALUE_RE.sub("[REDACTED]", message)
    return sanitized[:500]


def redact_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in mapping.items():
        if _is_forbidden_key(key):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


def assert_no_pii_keys(mapping: Mapping[str, object]) -> None:
    for key, value in mapping.items():
        validate_attribute_key(key)
        if isinstance(value, Mapping):
            assert_no_pii_keys(value)
