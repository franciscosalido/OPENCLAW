from __future__ import annotations

import json
import os
import sys
import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from opentelemetry import metrics, trace
from opentelemetry.metrics import Meter
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExportResult
from opentelemetry.trace import Tracer

_TRACING_INITIALIZED = False
_ACTIVE_PROVIDER: TracerProvider | None = None
_ASYNC_PG_INSTRUMENTED = False


class _SafeConsoleSpanExporter(ConsoleSpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return super().export(spans)
        except ValueError:
            return SpanExportResult.FAILURE


@dataclass(frozen=True)
class BatchSpanProcessorConfig:
    max_queue_size: int
    max_export_batch_size: int
    schedule_delay_millis: int
    export_timeout_millis: int


def is_otel_disabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def batch_span_processor_config() -> BatchSpanProcessorConfig:
    config = BatchSpanProcessorConfig(
        max_queue_size=_env_int("QUIMERA_OTEL_MAX_QUEUE_SIZE", 2048),
        max_export_batch_size=_env_int("QUIMERA_OTEL_MAX_EXPORT_BATCH_SIZE", 512),
        schedule_delay_millis=_env_int("QUIMERA_OTEL_SCHEDULE_DELAY_MILLIS", 5000),
        export_timeout_millis=_env_int("QUIMERA_OTEL_EXPORT_TIMEOUT_MILLIS", 30000),
    )
    if config.max_export_batch_size > config.max_queue_size:
        raise ValueError("QUIMERA_OTEL_MAX_EXPORT_BATCH_SIZE must be <= QUIMERA_OTEL_MAX_QUEUE_SIZE")
    return config


def build_resource() -> Resource:
    attrs: dict[str, str] = {
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "quimera"),
        DEPLOYMENT_ENVIRONMENT: os.getenv("QUIMERA_ENV", "local"),
        "quimera.project": "openclaw",
    }
    version = os.getenv("QUIMERA_VERSION")
    if version:
        attrs["service.version"] = version
    return Resource.create(attrs)


def _otlp_endpoint() -> str | None:
    traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if traces_endpoint:
        return traces_endpoint
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        return endpoint.rstrip("/") + "/v1/traces"
    return None


def _build_span_exporter() -> Any:
    endpoint = _otlp_endpoint()
    if endpoint is None:
        return _SafeConsoleSpanExporter()
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=endpoint)


def setup_tracing() -> None:
    global _ACTIVE_PROVIDER, _TRACING_INITIALIZED
    if _TRACING_INITIALIZED or is_otel_disabled():
        return
    config = batch_span_processor_config()
    provider = TracerProvider(resource=build_resource())
    processor = BatchSpanProcessor(
        _build_span_exporter(),
        max_queue_size=config.max_queue_size,
        max_export_batch_size=config.max_export_batch_size,
        schedule_delay_millis=config.schedule_delay_millis,
        export_timeout_millis=config.export_timeout_millis,
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _ACTIVE_PROVIDER = provider
    _TRACING_INITIALIZED = True


def setup_observability(*, instrument_asyncpg: bool = True) -> None:
    setup_tracing()
    if instrument_asyncpg:
        instrument_asyncpg_once()


def get_tracer(name: str) -> Tracer:
    setup_tracing()
    return trace.get_tracer(name)


def get_meter(name: str) -> Meter:
    from backend.observability.metrics import get_meter as _get_meter

    return _get_meter(name)


def shutdown_tracing() -> None:
    global _ACTIVE_PROVIDER, _ASYNC_PG_INSTRUMENTED, _TRACING_INITIALIZED
    if _ACTIVE_PROVIDER is not None:
        _ACTIVE_PROVIDER.shutdown()
    _ACTIVE_PROVIDER = None
    _TRACING_INITIALIZED = False
    _ASYNC_PG_INSTRUMENTED = False


def force_flush_tracing(timeout_millis: int = 30000) -> bool:
    if _ACTIVE_PROVIDER is None:
        return True
    return bool(_ACTIVE_PROVIDER.force_flush(timeout_millis=timeout_millis))


def instrument_asyncpg_once() -> None:
    global _ASYNC_PG_INSTRUMENTED
    if _ASYNC_PG_INSTRUMENTED or is_otel_disabled():
        return
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    except ImportError:
        logger.warning("otel_asyncpg_instrumentation_unavailable")
        return
    instrumentor_cls: Any = AsyncPGInstrumentor
    instrumentor_cls().instrument()
    _ASYNC_PG_INSTRUMENTED = True


def build_doctor_report(config_path: Path | None = None) -> dict[str, object]:
    from backend.observability.lite_llm import validate_litellm_otel_callback_config

    config = config_path or Path("infra/litellm/litellm_config.yaml")
    semconv = os.getenv("OTEL_SEMCONV_STABILITY_OPT_IN", "")
    backend_files = sorted(Path("backend/observability").glob("*.py"))
    imports_requests = any(_imports_module(path, "requests") for path in backend_files)
    try:
        import opentelemetry  # noqa: F401
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor  # noqa: F401

        packages_ok = True
        asyncpg_ok = True
    except ImportError:
        packages_ok = False
        asyncpg_ok = False
    litellm_validation = validate_litellm_otel_callback_config(config)
    checks = {
        "otel_sdk_disabled": is_otel_disabled(),
        "service_name": os.getenv("OTEL_SERVICE_NAME", "quimera"),
        "trace_exporter": "otlp_http" if _otlp_endpoint() else "console",
        "traces_endpoint": _otlp_endpoint(),
        "semconv_gen_ai_latest_experimental": (
            "gen_ai_latest_experimental" in {item.strip() for item in semconv.split(",") if item.strip()}
            if semconv
            else False
        ),
        "litellm_otel_callback": litellm_validation["callbacks_present"],
        "litellm_message_logging_disabled": litellm_validation["message_logging_disabled"],
        "backend_observability_imports_requests": imports_requests,
        "opentelemetry_packages_importable": packages_ok,
        "asyncpg_instrumentor_importable": asyncpg_ok,
    }
    status = "ok"
    if not checks["litellm_otel_callback"] or not checks["litellm_message_logging_disabled"] or imports_requests:
        status = "fail"
    elif semconv and not checks["semconv_gen_ai_latest_experimental"]:
        status = "warn"
    return {"status": status, "checks": checks}


def _imports_module(path: Path, module_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module_name or alias.name.startswith(f"{module_name}.") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == module_name or node.module.startswith(f"{module_name}."):
                return True
    return False


def _main() -> int:
    if "--doctor" not in sys.argv:
        return 0
    json_output = "--json" in sys.argv
    config = Path("infra/litellm/litellm_config.yaml")
    if "--config" in sys.argv:
        config = Path(sys.argv[sys.argv.index("--config") + 1])
    report = build_doctor_report(config)
    if json_output:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"otel-doctor status: {report['status']}")
        print(json.dumps(report["checks"], indent=2, sort_keys=True))
    return 0 if report["status"] in {"ok", "warn"} else 1


def _reset_for_tests() -> None:
    global _ACTIVE_PROVIDER, _ASYNC_PG_INSTRUMENTED, _TRACING_INITIALIZED
    _ACTIVE_PROVIDER = None
    _TRACING_INITIALIZED = False
    _ASYNC_PG_INSTRUMENTED = False


if __name__ == "__main__":
    raise SystemExit(_main())
