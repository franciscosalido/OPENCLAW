from __future__ import annotations

from pathlib import Path


START_QUIMERA = Path("scripts/start_quimera.sh")
START_LITELLM = Path("infra/litellm/start_litellm.sh")


def test_start_quimera_does_not_reintroduce_litellm_subcommands() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    for command in (
        "litellm-start",
        "litellm-stop",
        "litellm-audit",
        "litellm-fingerprint",
        "litellm-benchmark",
    ):
        assert f"{command})" not in text
    assert "--start) _start ;;" in text
    assert "--stop) _stop ;;" in text
    assert "--status) _status ;;" in text


def test_start_quimera_probes_host_litellm_without_owning_process() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    assert "/health/readiness" in text
    assert "_detect_litellm_runtime()" in text
    assert 'bash "${REPO_ROOT}/infra/litellm/start_litellm.sh"' not in text


def test_start_quimera_stop_does_not_kill_litellm_processes() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    assert ".runtime/litellm.pid" not in text
    assert 'kill -TERM "${pid}"' not in text
    assert 'kill -KILL "${pid}"' not in text
    assert "pkill" not in text
    assert "killall" not in text


def test_start_litellm_host_contract() -> None:
    text = START_LITELLM.read_text(encoding="utf-8")

    assert "litellm_docker_container_running" in text
    assert "Refusing to reuse quimera-litellm Docker container" in text
    assert "LITELLM_MODE=PRODUCTION" in text
    assert "LITELLM_LOG=ERROR" in text
    assert '--host "${LITELLM_HOST}"' in text
    assert '--port "${LITELLM_PORT}"' in text
    assert "--num_workers 1" in text
    assert "--telemetry False" in text
    assert "/health/readiness" in text
    assert "/health/liveliness" not in text
    assert "pkill" not in text
    assert "killall" not in text
