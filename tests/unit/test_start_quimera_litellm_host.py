from __future__ import annotations

from pathlib import Path


START_QUIMERA = Path("scripts/start_quimera.sh")
START_LITELLM = Path("infra/litellm/start_litellm.sh")


def test_start_quimera_litellm_commands_exist() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    for command in (
        "litellm-start",
        "litellm-stop",
        "litellm-audit",
        "litellm-fingerprint",
        "litellm-benchmark",
    ):
        assert f"{command})" in text


def test_litellm_start_uses_host_script() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    assert "bash \"${REPO_ROOT}/infra/litellm/start_litellm.sh\"" in text


def test_litellm_stop_uses_only_owned_pid_with_sigkill_fallback() -> None:
    text = START_QUIMERA.read_text(encoding="utf-8")

    assert ".runtime/litellm.pid" in text
    assert 'kill -TERM "${pid}"' in text
    assert 'kill -KILL "${pid}"' in text
    assert "pkill" not in text
    assert "killall" not in text


def test_start_litellm_host_contract() -> None:
    text = START_LITELLM.read_text(encoding="utf-8")

    assert "LITELLM_MODE=PRODUCTION" in text
    assert "LITELLM_LOG=ERROR" in text
    assert "--host \"${LITELLM_HOST}\"" in text
    assert "--port \"${LITELLM_PORT}\"" in text
    assert "--num_workers 1" in text
    assert "--telemetry False" in text
    assert "/health/readiness" in text
    assert "/health/liveliness" not in text
    assert "pkill" not in text
    assert "killall" not in text
