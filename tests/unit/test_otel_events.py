from __future__ import annotations

import pytest

from backend.observability.events import (
    add_cache_decision_event,
    add_evaluation_score,
    add_safe_event,
)


class FakeSpan:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def add_event(self, name: str, attributes: object | None = None) -> None:
        self.events.append((name, attributes))


def test_add_safe_event_records_valid_metadata_only() -> None:
    span = FakeSpan()

    add_safe_event(span, "quimera.retrieval.stage", {"quimera.stage": "pack"})

    assert span.events == [("quimera.retrieval.stage", {"quimera.stage": "pack"})]


def test_add_safe_event_rejects_prompt_payload() -> None:
    with pytest.raises(ValueError):
        add_safe_event(FakeSpan(), "quimera.retrieval.stage", {"quimera.prompt": "raw"})


def test_add_evaluation_score_records_genai_event() -> None:
    span = FakeSpan()

    add_evaluation_score(span, "faithfulness", 0.91, label="synthetic")

    assert span.events[0][0] == "gen_ai.evaluation.result"


def test_add_cache_decision_event_records_safe_reason() -> None:
    span = FakeSpan()

    add_cache_decision_event(span, hit=False, backend="qdrant", reason="schema_version_miss")

    assert span.events[0][1] == {
        "cache.hit": False,
        "cache.backend": "qdrant",
        "quimera.cache_reason": "schema_version_miss",
    }

