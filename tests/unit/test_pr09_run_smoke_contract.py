from __future__ import annotations

from pathlib import Path

from integration.smoke_summary import render_summary_table


SCRIPT = Path("run_smoke.sh")
START = Path("scripts/start_quimera.sh")


def test_run_smoke_script_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.exists()
    assert "set -euo pipefail" in text
    for flag in (
        "--quick",
        "--full",
        "--diagnostic",
        "--json",
        "--leave-running",
        "--no-build",
        "--timeout",
    ):
        assert flag in text
    assert "docker compose" in text
    assert "--wait" in text
    assert "poll_health_fallback" in text
    assert "rag_01b_pr09_smoke_summary.json" in text
    assert "down -v" not in text
    assert "docker system prune" not in text
    assert "delete_collection" not in text


def test_start_quimera_does_not_reintroduce_smoke_subcommand() -> None:
    text = START.read_text(encoding="utf-8")

    assert "smoke)" not in text
    assert "run_smoke.sh" not in text
    assert "--start) _start ;;" in text


def test_run_smoke_exit_codes_documented() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for expected in (
        "0: ok",
        "1: fail",
        "2: degraded",
        "3: configuration error",
        "4: backup/restore",
        "5: latency regression",
    ):
        assert expected in text


def test_render_summary_table_with_string_service_values() -> None:
    table = render_summary_table(
        {
            "services": {
                "postgres": "ok",
                "qdrant": {"status": "degraded"},
                "litellm": "fail",
                "mcp_postgres": {"status": "ok"},
            },
            "agentic0": {"status": "skipped"},
            "latency": {
                "postgres_p95_ms": 1.0,
                "qdrant_p95_ms": 2.0,
                "litellm_p95_ms": 3.0,
                "agentic0_p95_ms": 4.0,
            },
        }
    )

    assert "| Postgres | ok |" in table
    assert "| Qdrant | degraded |" in table
    assert "| LiteLLM | fail |" in table
    assert "| Agentic0 | skipped |" in table
