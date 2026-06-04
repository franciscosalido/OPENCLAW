from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from opentelemetry.trace import Status, StatusCode

from backend.observability.attributes import (
    CACHE_HIT,
    ERROR_TYPE,
    GEN_AI_AGENT_ID,
    GEN_AI_AGENT_NAME,
    GEN_AI_DATA_SOURCE_ID,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_TOOL_NAME,
    HYBRID_FUSION_BACKEND,
    LATENCY_EMBED_MS,
    LATENCY_LLM_MS,
    LATENCY_PG_MS,
    LATENCY_RETRIEVAL_MS,
    LATENCY_RRF_MS,
    MCP_METHOD_NAME,
    RETRIEVAL_RESULT_COUNT,
)
from backend.observability.context import get_quimera_context_attributes
from backend.observability.safety import sanitize_error_message, validate_attributes
from backend.observability.tracer import get_tracer

P = ParamSpec("P")
R = TypeVar("R")
AsyncCallable = Callable[P, Awaitable[R]]


def _ensure_async(fn: Callable[P, object]) -> AsyncCallable[P, R]:
    if not inspect.iscoroutinefunction(fn):
        raise TypeError("OpenTelemetry Quimera decorators support async functions only")
    return cast(AsyncCallable[P, R], fn)


def _duration_ms(start_ns: int) -> float:
    return (time.perf_counter_ns() - start_ns) / 1_000_000.0


def _set_attrs(span: Any, attrs: Mapping[str, object]) -> None:
    for key, value in validate_attributes(attrs).items():
        span.set_attribute(key, value)


def _result_count(result: object) -> int | None:
    if isinstance(result, Mapping):
        raw = result.get("result_count")
        if isinstance(raw, int):
            return raw
    if isinstance(result, list | tuple):
        return len(result)
    raw_attr = getattr(result, "result_count", None)
    return raw_attr if isinstance(raw_attr, int) else None


def _cache_hit(result: object) -> bool | None:
    if isinstance(result, Mapping):
        raw = result.get("cache_hit")
        if isinstance(raw, bool):
            return raw
    raw_attr = getattr(result, "cache_hit", None)
    return raw_attr if isinstance(raw_attr, bool) else None


def _trace_async(
    fn: Callable[P, object],
    *,
    span_name: str,
    base_attrs: Mapping[str, object],
    latency_attr: str,
    enrich_result: Callable[[object], Mapping[str, object]] | None = None,
) -> AsyncCallable[P, R]:
    async_fn: AsyncCallable[P, R] = _ensure_async(fn)

    @wraps(async_fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        tracer = get_tracer("quimera.observability")
        attrs = {**get_quimera_context_attributes(), **dict(base_attrs)}
        with tracer.start_as_current_span(span_name, attributes=validate_attributes(attrs)) as span:
            start_ns = time.perf_counter_ns()
            try:
                result = await async_fn(*args, **kwargs)
            except Exception as exc:
                _set_attrs(span, {latency_attr: _duration_ms(start_ns), ERROR_TYPE: type(exc).__name__})
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, sanitize_error_message(str(exc))))
                raise
            _set_attrs(span, {latency_attr: _duration_ms(start_ns)})
            if enrich_result is not None:
                _set_attrs(span, enrich_result(result))
            return result

    return wrapper


def traced_embed(model: str | None = None) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        attrs: dict[str, object] = {
            GEN_AI_OPERATION_NAME: "embeddings",
            GEN_AI_PROVIDER_NAME: "ollama",
        }
        if model:
            attrs[GEN_AI_REQUEST_MODEL] = model
        return _trace_async(fn, span_name="embeddings", base_attrs=attrs, latency_attr=LATENCY_EMBED_MS)

    return decorator


def traced_llm(
    model: str | None = None,
    *,
    operation: str = "chat",
) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        attrs: dict[str, object] = {
            GEN_AI_OPERATION_NAME: operation,
            GEN_AI_PROVIDER_NAME: "ollama",
        }
        if model:
            attrs[GEN_AI_REQUEST_MODEL] = model
        return _trace_async(fn, span_name=f"{operation} {model or 'local'}", base_attrs=attrs, latency_attr=LATENCY_LLM_MS)

    return decorator


def traced_retrieval(source: str | None = None) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def enrich(result: object) -> Mapping[str, object]:
        attrs: dict[str, object] = {}
        count = _result_count(result)
        hit = _cache_hit(result)
        if count is not None:
            attrs[RETRIEVAL_RESULT_COUNT] = count
        if hit is not None:
            attrs[CACHE_HIT] = hit
        return attrs

    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        attrs = {GEN_AI_OPERATION_NAME: "retrieval"}
        if source:
            attrs[GEN_AI_DATA_SOURCE_ID] = source
        return _trace_async(
            fn,
            span_name=f"retrieval {source or 'local'}",
            base_attrs=attrs,
            latency_attr=LATENCY_RETRIEVAL_MS,
            enrich_result=enrich,
        )

    return decorator


def traced_rrf(*, backend: str = "python_rrf") -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        return _trace_async(
            fn,
            span_name="retrieval rrf",
            base_attrs={HYBRID_FUSION_BACKEND: backend},
            latency_attr=LATENCY_RRF_MS,
        )

    return decorator


def traced_pg(table: str, operation: str) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        return _trace_async(
            fn,
            span_name=f"pg {operation} {table}",
            base_attrs={"quimera.pg_table": table, "quimera.pg_operation": operation},
            latency_attr=LATENCY_PG_MS,
        )

    return decorator


def traced_agent(
    agent_name: str,
    agent_id: str | None = None,
) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        attrs: dict[str, object] = {
            GEN_AI_AGENT_NAME: agent_name,
        }
        if agent_id:
            attrs[GEN_AI_AGENT_ID] = agent_id
        return _trace_async(fn, span_name=f"agent {agent_name}", base_attrs=attrs, latency_attr="latency.total_ms")

    return decorator


def traced_mcp_tool(
    tool_name: str,
    *,
    method_name: str = "tools/call",
) -> Callable[[Callable[P, object]], AsyncCallable[P, R]]:
    def decorator(fn: Callable[P, object]) -> AsyncCallable[P, R]:
        return _trace_async(
            fn,
            span_name=f"mcp {tool_name}",
            base_attrs={GEN_AI_TOOL_NAME: tool_name, MCP_METHOD_NAME: method_name},
            latency_attr="latency.total_ms",
        )

    return decorator
