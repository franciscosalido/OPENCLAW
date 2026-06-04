from __future__ import annotations

from pathlib import Path


START = Path("scripts/start_quimera.sh")


def test_start_quimera_declares_otel_doctor_command() -> None:
    text = START.read_text(encoding="utf-8")

    assert "otel-doctor" in text
    assert "otel_doctor()" in text
    assert "backend.observability.tracer --doctor" in text


def test_start_quimera_supports_otel_doctor_json_flag() -> None:
    text = START.read_text(encoding="utf-8")

    assert "--json) OTEL_JSON=1" in text
    assert "--doctor --json" in text

