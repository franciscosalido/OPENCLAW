from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import metrics
from opentelemetry.metrics import Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider

from backend.observability.safety import validate_attributes
from backend.observability.tracer import build_resource, is_otel_disabled

_METRICS_INITIALIZED = False
_GENAI_OPERATION_DURATION: Histogram | None = None
_RETRIEVAL_OPERATION_DURATION: Histogram | None = None


def setup_metrics() -> None:
    global _GENAI_OPERATION_DURATION, _METRICS_INITIALIZED, _RETRIEVAL_OPERATION_DURATION
    if _METRICS_INITIALIZED or is_otel_disabled():
        return
    provider = MeterProvider(resource=build_resource())
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter("quimera.observability")
    _GENAI_OPERATION_DURATION = meter.create_histogram(
        "gen_ai.client.operation.duration",
        unit="s",
        description="Duration of local GenAI client operations.",
    )
    _RETRIEVAL_OPERATION_DURATION = meter.create_histogram(
        "quimera.retrieval.operation.duration",
        unit="ms",
        description="Duration of Quimera retrieval operations.",
    )
    _METRICS_INITIALIZED = True


def get_meter(name: str = "quimera.observability") -> Meter:
    setup_metrics()
    return metrics.get_meter(name)


def record_genai_operation_duration(
    duration_ms: float,
    attributes: Mapping[str, object] | None = None,
) -> None:
    setup_metrics()
    if _GENAI_OPERATION_DURATION is None:
        return
    _GENAI_OPERATION_DURATION.record(duration_ms / 1000.0, validate_attributes(attributes))


def record_retrieval_duration(
    duration_ms: float,
    attributes: Mapping[str, object] | None = None,
) -> None:
    setup_metrics()
    if _RETRIEVAL_OPERATION_DURATION is None:
        return
    _RETRIEVAL_OPERATION_DURATION.record(duration_ms, validate_attributes(attributes))


def _reset_for_tests() -> None:
    global _GENAI_OPERATION_DURATION, _METRICS_INITIALIZED, _RETRIEVAL_OPERATION_DURATION
    _METRICS_INITIALIZED = False
    _GENAI_OPERATION_DURATION = None
    _RETRIEVAL_OPERATION_DURATION = None
