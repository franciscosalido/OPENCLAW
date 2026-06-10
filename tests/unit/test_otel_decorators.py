from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from types import TracebackType
from typing import Any, cast

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

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

    def add_event(self, name: str, attributes: Mapping[str, object]) -> None:
        self.attributes[f"event.{name}.type"] = attributes.get("exception.type", "")
        self.attributes[f"event.{name}.message"] = attributes.get(
            "exception.message", ""
        )

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
        **_: object,
    ) -> FakeSpanContext:
        self.span_names.append(name)
        return FakeSpanContext(self.span, attributes)


def _memory_tracer() -> tuple[Any, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("quimera-test"), exporter


def _only_finished_span(exporter: InMemorySpanExporter) -> Any:
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


async def test_traced_llm_sets_model_context_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


async def test_traced_retrieval_records_result_count_and_cache_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_retrieval(source="qdrant")
    async def retrieve() -> dict[str, Any]:
        return {"result_count": 3, "cache_hit": True}

    await retrieve()

    assert tracer.span.attributes["retrieval.result_count"] == 3
    assert tracer.span.attributes["cache.hit"] is True


async def test_decorator_records_exception_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_pg(table="sessions", operation="select")
    async def broken() -> None:
        raise RuntimeError("bad postgresql://user:secret@localhost/db")

    with pytest.raises(RuntimeError):
        await broken()

    assert tracer.span.attributes["error.type"] == "RuntimeError"
    assert tracer.span.attributes["event.exception.type"] == "RuntimeError"
    assert tracer.span.attributes["event.exception.message"] == "bad [REDACTED]"
    assert tracer.span.status is not None


async def test_traced_embed_emits_real_finished_span_without_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer, exporter = _memory_tracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_embed(model="nomic-embed-text")
    async def embed(query_text: str, vector: list[float]) -> list[float]:
        assert query_text == "private prompt text"
        assert vector == [0.1, 0.2]
        return [0.3, 0.4]

    assert await embed("private prompt text", [0.1, 0.2]) == [0.3, 0.4]

    span = _only_finished_span(exporter)
    attrs = span.attributes
    assert span.name == "embeddings"
    assert attrs["gen_ai.operation.name"] == "embeddings"
    assert attrs["gen_ai.provider.name"] == "ollama"
    assert attrs["gen_ai.request.model"] == "nomic-embed-text"
    assert attrs["latency.embed_ms"] >= 0
    assert "private prompt text" not in repr(attrs)
    assert "0.1" not in repr(attrs)


async def test_traced_retrieval_emits_real_span_with_result_count_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer, exporter = _memory_tracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_retrieval(source="qdrant")
    async def retrieve() -> list[dict[str, str]]:
        return [{"id": "a"}, {"id": "b"}]

    assert await retrieve() == [{"id": "a"}, {"id": "b"}]

    span = _only_finished_span(exporter)
    attrs = span.attributes
    assert span.name == "retrieval qdrant"
    assert attrs["gen_ai.operation.name"] == "retrieval"
    assert attrs["gen_ai.data_source.id"] == "qdrant"
    assert attrs["retrieval.result_count"] == 2
    assert attrs["latency.retrieval_ms"] >= 0


async def test_traced_rrf_emits_real_span_with_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer, exporter = _memory_tracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_rrf(backend="python_rrf")
    async def fuse() -> tuple[str, ...]:
        return ("doc-a", "doc-b")

    assert await fuse() == ("doc-a", "doc-b")

    span = _only_finished_span(exporter)
    attrs = span.attributes
    assert span.name == "retrieval rrf"
    assert attrs["hybrid.fusion.backend"] == "python_rrf"
    assert attrs["latency.rrf_ms"] >= 0


@pytest.mark.parametrize(
    ("operation", "result", "expected_hit"),
    (("lookup", {"doc": "a"}, True), ("lookup", None, False), ("store", True, False)),
)
async def test_traced_cache_emits_real_span_with_cache_contract(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    result: object,
    expected_hit: bool,
) -> None:
    tracer, exporter = _memory_tracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_cache(
        operation=operation,
        backend="qdrant",
        collection="quimera_query_cache",
    )
    async def cache_call() -> object:
        return result

    assert await cache_call() is result

    span = _only_finished_span(exporter)
    attrs = span.attributes
    assert span.name == f"cache {operation}"
    assert attrs["cache.backend"] == "qdrant"
    assert attrs["cache.collection"] == "quimera_query_cache"
    assert attrs["cache.hit"] is expected_hit
    assert attrs["retrieval.cache_hit"] is expected_hit
    assert attrs["latency.retrieval_ms"] >= 0


async def test_traced_pg_exception_span_sanitizes_status_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer, exporter = _memory_tracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_pg(table="sessions", operation="select")
    async def broken() -> None:
        raise RuntimeError("failed postgresql://user:secret@localhost/db")

    with pytest.raises(RuntimeError):
        await broken()

    span = _only_finished_span(exporter)
    event = span.events[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "failed [REDACTED]"
    assert span.attributes["error.type"] == "RuntimeError"
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert event.attributes["exception.message"] == "failed [REDACTED]"
    assert "secret" not in repr(span.status)
    assert "secret" not in repr(event.attributes)


async def test_traced_pg_sets_postgresql_semconv_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_pg(table="sessions", operation="select")
    async def query() -> None:
        return None

    await query()

    assert tracer.span.attributes["db.system.name"] == "postgresql"
    assert tracer.span.attributes["db.operation.name"] == "SELECT"
    assert tracer.span.attributes["db.collection.name"] == "sessions"
    assert tracer.span.attributes["quimera.pg_table"] == "sessions"
    assert tracer.span.attributes["quimera.pg_operation"] == "SELECT"


async def test_traced_mcp_tool_uses_method_span_name_and_safe_tool_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(decorators, "get_tracer", lambda name: tracer)

    @decorators.traced_mcp_tool(tool_name="safe_tool")
    async def call_tool() -> None:
        return None

    await call_tool()

    assert tracer.span_names == ["mcp tools/call"]
    assert tracer.span.attributes["gen_ai.operation.name"] == "execute_tool"
    assert tracer.span.attributes["gen_ai.tool.name"] == "safe_tool"


def test_traced_mcp_tool_rejects_sensitive_or_free_text_tool_name() -> None:
    with pytest.raises(ValueError):
        decorators.traced_mcp_tool(tool_name="dump_prompt please")


def test_decorator_rejects_sync_functions() -> None:
    with pytest.raises(TypeError, match="async functions only"):

        def sync_fn() -> None:
            return None

        decorators.traced_embed(model="nomic-embed-text")(
            cast(Callable[[], Awaitable[None]], sync_fn)
        )
