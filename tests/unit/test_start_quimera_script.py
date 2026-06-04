from __future__ import annotations

import os
from pathlib import Path


SCRIPT = Path("scripts/start_quimera.sh")
STAR_WRAPPER = Path("scripts/star_quimera.sh")
COMPOSE = Path("infra/docker/compose.quimera.local.yml")
SDD = Path("docs/specs/rag-01b/pr-04-ollama-tuning-keepalive.md")
ENV_EXAMPLE = Path(".env.local.example")


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


def test_compose_requires_litellm_master_key_fail_fast() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY:?" in text


def test_local_env_example_documents_litellm_master_key() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "LITELLM_MASTER_KEY=quimera-dev-key" in text
    assert "QUIMERA_LLM_API_KEY=${LITELLM_MASTER_KEY}" in text


def test_sdd_documents_manual_volume_reset_policy() -> None:
    text = SDD.read_text(encoding="utf-8").lower()

    assert "reset de volume" in text
    assert "manual" in text
    assert "docker volume rm" in text
