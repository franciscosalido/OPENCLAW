from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

FORBIDDEN_OTEL_ATTRIBUTE_PARTS = frozenset(
    {
        "prompt",
        "answer",
        "response",
        "chunk",
        "document_text",
        "vector",
        "embedding",
        "authorization",
        "api_key",
        "secret",
        "password",
        "dsn",
    }
)


class SpanAttributeSummary(TypedDict):
    observed_span_names: list[str]
    observed_safe_attributes: dict[str, object]
    forbidden_attributes_seen: list[str]


def summarize_span_attributes(spans: Sequence[object]) -> SpanAttributeSummary:
    names: list[str] = []
    safe: dict[str, object] = {}
    forbidden: list[str] = []
    for span in spans:
        names.append(str(getattr(span, "name", "")))
        attributes = getattr(span, "attributes", {}) or {}
        if isinstance(attributes, Mapping):
            for key, value in attributes.items():
                key_text = str(key)
                if any(part in key_text.lower() for part in FORBIDDEN_OTEL_ATTRIBUTE_PARTS):
                    forbidden.append(key_text)
                else:
                    safe[key_text] = value
    return {
        "observed_span_names": names,
        "observed_safe_attributes": safe,
        "forbidden_attributes_seen": sorted(set(forbidden)),
    }
