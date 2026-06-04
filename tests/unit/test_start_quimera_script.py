from __future__ import annotations

import os
from pathlib import Path


SCRIPT = Path("scripts/start_quimera.sh")
STAR_WRAPPER = Path("scripts/star_quimera.sh")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_start_quimera_script_exists_and_is_executable() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)


def test_start_quimera_script_declares_required_subcommands() -> None:
    text = _script_text()

    for command in (
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "doctor",
        "test",
        "warmup",
        "release",
    ):
        assert f"{command})" in text


def test_start_quimera_exports_ollama_tuning_env() -> None:
    text = _script_text()

    assert "export OLLAMA_KEEP_ALIVE" in text
    assert "export OLLAMA_NUM_PARALLEL" in text
    assert "export OLLAMA_MAX_LOADED_MODELS" in text


def test_start_quimera_uses_compose_without_destructive_prune() -> None:
    text = _script_text()

    assert "compose.quimera.local.yml" in text
    assert "docker compose" in text
    assert " up -d" in text
    assert "down -v" not in text
    assert "docker system prune" not in text


def test_start_quimera_does_not_kill_external_ollama() -> None:
    text = _script_text()

    assert "killall ollama" not in text
    assert "pkill ollama" not in text
    assert ".runtime/ollama.pid" in text


def test_start_quimera_wires_warmup_and_release_hooks() -> None:
    text = _script_text()

    assert "infra/ollama/warmup.py" in text
    assert "infra/ollama/shutdown_hook.py" in text
    assert "--warmup" in text
    assert "--release-models" in text


def test_star_quimera_wrapper_execs_start_script() -> None:
    assert STAR_WRAPPER.exists()
    text = STAR_WRAPPER.read_text(encoding="utf-8")

    assert 'exec "$(dirname "$0")/start_quimera.sh" "$@"' in text
