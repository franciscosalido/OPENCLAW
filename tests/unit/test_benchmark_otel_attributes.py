from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from backend.observability import decorators
from evaluation.benchmark_otlp import summarize_span_attributes
from evaluation.compare_session_context_backends import (
    benchmark_cache_lookup_probe,
    benchmark_embed_probe,
    benchmark_pg_read_probe,
    benchmark_pg_write_probe,
    benchmark_rerank_probe,
    benchmark_retrieval_probe,
    benchmark_rrf_probe,
)


async def test_benchmark_otel_attributes_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(decorators, "get_tracer", provider.get_tracer)

    await benchmark_embed_probe()
    await benchmark_retrieval_probe()
    await benchmark_cache_lookup_probe()
    await benchmark_rrf_probe()
    await benchmark_rerank_probe()
    await benchmark_pg_read_probe()
    await benchmark_pg_write_probe()

    summary = summarize_span_attributes(exporter.get_finished_spans())
    attrs = summary["observed_safe_attributes"]

    assert "embeddings" in summary["observed_span_names"]
    assert "retrieval qdrant" in summary["observed_span_names"]
    assert "retrieval rerank" in summary["observed_span_names"]
    assert "cache lookup" in summary["observed_span_names"]
    assert attrs["gen_ai.operation.name"] == "retrieval"
    assert attrs["db.system.name"] == "postgresql"
    assert "latency.rrf_ms" in attrs
    assert "latency.rerank_ms" in attrs
    assert attrs["cache.backend"] == "qdrant"
    assert summary["forbidden_attributes_seen"] == []
