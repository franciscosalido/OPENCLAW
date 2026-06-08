from __future__ import annotations

from pathlib import Path

import pytest

from backend.observability import tracer


def test_is_otel_disabled_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    assert tracer.is_otel_disabled() is True


def test_batch_config_validates_export_batch_not_larger_than_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUIMERA_OTEL_MAX_QUEUE_SIZE", "4")
    monkeypatch.setenv("QUIMERA_OTEL_MAX_EXPORT_BATCH_SIZE", "5")

    with pytest.raises(ValueError):
        tracer.batch_span_processor_config()


def test_build_resource_uses_quimera_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("QUIMERA_ENV", raising=False)

    attrs = tracer.build_resource().attributes

    assert attrs["service.name"] == "quimera"
    assert attrs["deployment.environment"] == "local"
    assert attrs["quimera.project"] == "openclaw"


def test_setup_tracing_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer._reset_for_tests()
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    tracer.setup_tracing()

    assert tracer._ACTIVE_PROVIDER is None


def test_doctor_report_checks_litellm_callback_and_no_requests_import() -> None:
    report = tracer.build_doctor_report(Path("infra/litellm/litellm_config.yaml"))

    assert isinstance(report["checks"], dict)
    checks = report["checks"]
    assert checks["backend_observability_imports_requests"] is False
    assert checks["opentelemetry_packages_importable"] is True
