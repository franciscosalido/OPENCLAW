from __future__ import annotations

from backend.observability.tracer import force_flush_tracing, setup_tracing, shutdown_tracing


def test_otel_console_exporter_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    setup_tracing()

    assert force_flush_tracing(timeout_millis=1000) is True
    shutdown_tracing()

