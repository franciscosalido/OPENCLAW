from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from backend.observability.attributes import (
    CACHE_BACKEND,
    CACHE_HIT,
    GEN_AI_EVALUATION_NAME,
    GEN_AI_EVALUATION_SCORE,
)
from backend.observability.safety import validate_attribute_key, validate_attributes


class EventSpan(Protocol):
    def add_event(self, name: str, attributes: Mapping[str, object] | None = None) -> None: ...


def add_safe_event(
    span: EventSpan,
    name: str,
    attributes: Mapping[str, object] | None = None,
) -> None:
    validate_attribute_key(f"quimera.{name}" if "." not in name else name)
    span.add_event(name, validate_attributes(attributes))


def add_evaluation_score(
    span: EventSpan,
    metric_name: str,
    score: float,
    label: str | None = None,
) -> None:
    if not math.isfinite(score):
        raise ValueError("evaluation score must be finite")
    attrs: dict[str, object] = {
        GEN_AI_EVALUATION_NAME: metric_name,
        GEN_AI_EVALUATION_SCORE: score,
    }
    if label is not None:
        attrs["quimera.evaluation_label"] = label
    add_safe_event(span, "gen_ai.evaluation.result", attrs)


def add_cache_decision_event(
    span: EventSpan,
    *,
    hit: bool,
    backend: str,
    reason: str | None = None,
) -> None:
    attrs: dict[str, object] = {
        CACHE_HIT: hit,
        CACHE_BACKEND: backend,
    }
    if reason is not None:
        attrs["quimera.cache_reason"] = reason
    add_safe_event(span, "quimera.cache.decision", attrs)

