from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any

import pytest

from backend.observability import decorators
from backend.observability.context import clear_quimera_context, set_quimera_context


class FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.exceptions: list[Exception] = []
        self.status: object | None = None

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: Exception) -> None:
        self.exceptions.append(exc)

    def set_status(self, status: object) -> None:
        self.status = status


class FakeSpanContext:
    def __init__(self, span: FakeSpan, attributes: Mapping[str, object] | None) -> None:
        self.span = span
        if attributes:
            self.span.attributes.update(attributes)

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeTracer:
    def __init__(self) -> None:
        self.span = FakeSpan()
        self.span_names: list[str] = []

    def start_as_current_span(
        self,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> FakeSpanContext:
        self.span_names.append(name)
        return FakeSpanContext(self.span, attributes)


async def test_traced_llm_sets_model_context_and_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)
    clear_quimera_context()
    set_quimera_context(session_id="s-1")

    @decorators.traced_llm(model="qwen3:14b")
    async def call() -> dict[str, str]:
        return {"ok": "yes"}

    assert await call() == {"ok": "yes"}
    assert getattr(call, "__wrapped__") is not None
    assert tracer.span.attributes["gen_ai.operation.name"] == "chat"
    assert tracer.span.attributes["gen_ai.request.model"] == "qwen3:14b"
    assert tracer.span.attributes["quimera.session_id"] == "s-1"
    assert "latency.llm_ms" in tracer.span.attributes


async def test_traced_retrieval_records_result_count_and_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_retrieval(source="qdrant")
    async def retrieve() -> dict[str, Any]:
        return {"result_count": 3, "cache_hit": True}

    await retrieve()

    assert tracer.span.attributes["retrieval.result_count"] == 3
    assert tracer.span.attributes["cache.hit"] is True


async def test_decorator_records_exception_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_pg(table="sessions", operation="select")
    async def broken() -> None:
        raise RuntimeError("bad postgresql://user:secret@localhost/db")

    with pytest.raises(RuntimeError):
        await broken()

    assert tracer.span.attributes["error.type"] == "RuntimeError"
    assert tracer.span.exceptions
    assert tracer.span.status is not None


def test_decorator_rejects_sync_functions() -> None:
    with pytest.raises(TypeError, match="async functions only"):

        @decorators.traced_embed(model="nomic-embed-text")
        def sync_fn() -> None:
            return None
