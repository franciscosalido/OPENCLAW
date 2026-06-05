from __future__ import annotations

from pathlib import Path


SCRIPT = Path("run_smoke.sh")
START = Path("scripts/start_quimera.sh")


def test_run_smoke_script_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.exists()
    assert "set -euo pipefail" in text
    for flag in ("--quick", "--full", "--diagnostic", "--json", "--leave-running", "--no-build", "--timeout"):
        assert flag in text
    assert "docker compose" in text
    assert "--wait" in text
    assert "poll_health_fallback" in text
    assert "rag_01b_pr09_smoke_summary.json" in text
    assert "down -v" not in text
    assert "docker system prune" not in text
    assert "delete_collection" not in text


def test_start_quimera_exposes_smoke_command() -> None:
    text = START.read_text(encoding="utf-8")

    assert "smoke)" in text
    assert "run_smoke.sh" in text


def test_run_smoke_exit_codes_documented() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for expected in ("0: ok", "1: fail", "2: degraded", "3: configuration error", "4: backup/restore", "5: latency regression"):
        assert expected in text
