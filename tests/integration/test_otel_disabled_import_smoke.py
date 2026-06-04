from __future__ import annotations

from backend.observability.tracer import setup_observability


def test_otel_disabled_import_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    setup_observability()

