from __future__ import annotations

import os
from pathlib import Path


SCRIPT = Path("scripts/start_quimera.sh")
STAR_WRAPPER = Path("scripts/star_quimera.sh")
COMPOSE = Path("infra/docker/compose.quimera.local.yml")
PR04_SDD = Path("docs/specs/rag-01b/pr-04-ollama-tuning-keepalive.md")
PR05_SDD = Path("docs/specs/rag-01b/pr-05-litellm-host-cache-timeout.md")
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
        "litellm-validate",
        "litellm-render",
        "litellm-start",
        "litellm-stop",
        "litellm-restart",
        "litellm-smoke",
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


def test_compose_does_not_manage_litellm() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "quimera-litellm" not in text
    assert "berriai/litellm" not in text
    assert "docker.litellm.ai" not in text
    assert "127.0.0.1:4000:4000" not in text
    assert "\n  litellm:" not in text


def test_start_quimera_does_not_kill_external_ollama() -> None:
    text = _script_text()

    assert "killall ollama" not in text
    assert "pkill ollama" not in text
    assert ".runtime/ollama.pid" in text


def test_start_quimera_controls_only_own_litellm_pid() -> None:
    text = _script_text()

    assert "pkill litellm" not in text
    assert "killall litellm" not in text
    assert ".runtime/litellm.pid" in text
    assert "litellm_start()" in text
    assert "litellm_stop()" in text
    assert 'kill -TERM "${pid}"' in text
    assert 'kill -KILL "${pid}"' in text


def test_start_quimera_reuses_existing_litellm_gateway() -> None:
    text = _script_text()

    assert "litellm_readiness_ok" in text
    assert "already running" in text
    assert "return 0" in text


def test_start_quimera_warns_on_placeholder_litellm_master_key() -> None:
    text = _script_text()

    assert "QUIMERA_DEV_LITELLM_PLACEHOLDER_KEY" in text
    assert "placeholder LITELLM_MASTER_KEY" in text


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


def test_compose_does_not_require_litellm_master_key() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "LITELLM_MASTER_KEY" not in text


def test_local_env_example_documents_litellm_master_key() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "LITELLM_MASTER_KEY=quimera-dev-key" in text
    assert "QUIMERA_LLM_API_KEY=${LITELLM_MASTER_KEY}" in text


def test_sdd_documents_manual_volume_reset_policy() -> None:
    text = PR04_SDD.read_text(encoding="utf-8").lower()

    assert "reset de volume" in text
    assert "manual" in text
    assert "docker volume rm" in text


def test_pr05_sdd_documents_litellm_host_policy() -> None:
    text = PR05_SDD.read_text(encoding="utf-8")

    assert "LiteLLM e um processo Python local do host" in text
    assert "Docker Compose nao gerencia LiteLLM" in text
    assert "Compose gerencia apenas Postgres e Qdrant" in text
