from __future__ import annotations

from pathlib import Path


START = Path("scripts/start_quimera.sh")


def test_start_quimera_does_not_reintroduce_otel_doctor_subcommand() -> None:
    text = START.read_text(encoding="utf-8")

    assert "otel-doctor" not in text
    assert "otel_doctor()" not in text
    assert "backend.observability.tracer --doctor" not in text


def test_start_quimera_accepts_only_start_stop_status_flags() -> None:
    text = START.read_text(encoding="utf-8")

    assert "--start) _start ;;" in text
    assert "--stop) _stop ;;" in text
    assert "--status) _status ;;" in text
    assert "--json) OTEL_JSON=1" not in text
