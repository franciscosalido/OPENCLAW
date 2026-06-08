from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.working_memory.models import (
    SCHEMA_VERSION_POINT_V1,
    MemoryKind,
    WorkingMemoryPoint,
)


NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def _point(**overrides: object) -> WorkingMemoryPoint:
    values: dict[str, object] = {
        "point_id": "wm-1",
        "agent_id": "agent-1",
        "session_id": uuid4(),
        "memory_kind": "turn_summary",
        "vector": (0.1, 0.2, 0.3, 0.4),
        "vector_dim": 4,
        "safe_summary": "short safe summary",
        "importance": 0.5,
        "recency_ts": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "expires_at": NOW + timedelta(seconds=60),
        "ttl_seconds": 60,
        "embedding_model": "nomic-embed-text",
        "metadata": {"safe": True},
    }
    values.update(overrides)
    return WorkingMemoryPoint(**values)  # type: ignore[arg-type]


def test_working_memory_point_defaults_and_payload_are_safe() -> None:
    point = _point()
    payload = point.to_qdrant_payload()

    assert point.schema_version == SCHEMA_VERSION_POINT_V1
    assert point.memory_kind == "turn_summary"
    assert payload["schema_version"] == SCHEMA_VERSION_POINT_V1
    assert payload["safe_summary"] == "short safe summary"
    assert "vector" not in payload
    assert "payload_checksum" in payload


@pytest.mark.parametrize("kind", list(MemoryKind.__args__))  # type: ignore[attr-defined]
def test_memory_kind_contract(kind: str) -> None:
    assert _point(memory_kind=kind).memory_kind == kind


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("agent_id", " ", "agent_id"),
        ("point_id", " ", "point_id"),
        ("importance", -0.1, "importance"),
        ("importance", 1.1, "importance"),
        ("expires_at", NOW, "expires_at"),
        ("ttl_seconds", 0, "ttl_seconds"),
        ("vector_dim", 3, "vector_dim"),
        ("safe_summary", "x" * 513, "safe_summary"),
        ("metadata", {"prompt": "bad"}, "sensitive"),
    ],
)
def test_working_memory_point_validation(field: str, value: object, match: str) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        _point(**{field: value})


def test_working_memory_point_repr_does_not_leak_summary_or_vector() -> None:
    point = _point(
        safe_summary="classified but safe short text", vector=(0.1, 0.2, 0.3, 0.4)
    )

    rendered = repr(point)

    assert "classified" not in rendered
    assert "0.1" not in rendered
    assert "vector_dim=4" in rendered
