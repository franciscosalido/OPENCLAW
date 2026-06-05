from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evaluation.benchmark_otlp import summarize_span_attributes

pytestmark = pytest.mark.integration


def test_pr08_otlp_trace_safety_contract() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("pr08-test")
    for name in ("agentic0.smoke", "integration.health", "litellm.chat", "mcp.postgres.tool", "mcp.qdrant.tool", "qdrant.hybrid_query", "postgres.memory_context"):
        with tracer.start_as_current_span(name) as span:
            span.set_attribute("quimera.correlation_id", "trace-safe")
            span.set_attribute("gen_ai.operation.name", "integration")

    summary = summarize_span_attributes(exporter.get_finished_spans())

    assert "agentic0.smoke" in summary["observed_span_names"]
    assert "mcp.postgres.tool" in summary["observed_span_names"]
    assert summary["forbidden_attributes_seen"] == []
