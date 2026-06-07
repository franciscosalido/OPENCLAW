from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


ROOT_SCRIPT = Path("start_quimera.sh")
SCRIPT = Path("scripts/start_quimera.sh")
STAR_WRAPPER = Path("scripts/star_quimera.sh")
COMPOSE = Path("infra/docker/compose.quimera.local.yml")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_start_quimera_script_exists_and_is_executable() -> None:
    assert ROOT_SCRIPT.exists()
    assert SCRIPT.exists()
    assert os.access(ROOT_SCRIPT, os.X_OK)
    assert os.access(SCRIPT, os.X_OK)


def test_shell_syntax_is_valid() -> None:
    subprocess.run(["bash", "-n", str(ROOT_SCRIPT)], check=True)
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    subprocess.run(["bash", "-n", str(STAR_WRAPPER)], check=True)


def test_accepts_exactly_start_stop_status_flags() -> None:
    text = _script_text()

    assert "--start) _start ;;" in text
    assert "--stop) _stop ;;" in text
    assert "--status) _status ;;" in text
    for legacy in (
        "restart)",
        "logs)",
        "doctor)",
        "test)",
        "warmup)",
        "release)",
        "litellm-start)",
        "litellm-stop)",
        "smoke)",
    ):
        assert legacy not in text


def test_invalid_arguments_print_usage_and_exit_2_contract() -> None:
    text = _script_text()

    assert "_usage" in text
    assert "exit 2" in text
    assert "Usage:" in text


def test_required_functions_exist() -> None:
    text = _script_text()

    for function_name in (
        "_log",
        "_warn",
        "_err",
        "_die",
        "_load_env",
        "_detect_compose_file",
        "_compose",
        "_service_exists",
        "_service_container_id",
        "_service_image_current",
        "_service_image_expected",
        "_service_config_hash_current",
        "_service_config_hash_expected",
        "_wait_service_healthy",
        "_wait_http_200",
        "_check_docker",
        "_detect_postgres_service",
        "_detect_qdrant_service",
        "_detect_litellm_runtime",
        "_detect_ollama_runtime",
        "_rebuild_postgres_if_needed",
        "_warmup_ollama_models",
        "_release_ollama_models",
        "_run_shutdown_hooks",
        "_status_table",
        "_start",
        "_stop",
        "_status",
        "_usage",
    ):
        assert re.search(rf"^{function_name}\(\) \{{", text, re.MULTILINE)


def test_rebuild_postgres_preserves_data_and_requires_human_confirmation() -> None:
    text = _script_text()

    assert "_rebuild_postgres_if_needed()" in text
    assert "POSTGRES REBUILD DETECTADO" in text
    assert "Volume de dados SERÁ PRESERVADO" in text
    assert "Confirmar rebuild? [s/N]" in text
    assert "read -r confirm" in text
    assert "Rebuild Postgres cancelado pelo operador" in text
    assert 'exit 0' in text


def test_rebuild_uses_safe_recreate_without_volume_removal() -> None:
    text = _script_text()

    assert 'docker inspect -f \'{{.Config.Image}}\'' in text
    assert 'docker inspect -f \'{{.Image}}\'' in text
    assert '_compose stop "${POSTGRES_SERVICE}"' in text
    assert '_compose rm -f "${POSTGRES_SERVICE}"' in text
    assert '_compose up -d "${POSTGRES_SERVICE}"' in text
    assert "-v" not in _line_containing(text, '_compose rm -f "${POSTGRES_SERVICE}"')


def test_script_contains_no_forbidden_destructive_operations() -> None:
    text = _script_text()

    forbidden = (
        "down -v",
        "docker system prune",
        "docker volume rm",
        "docker volume prune",
        "--volumes",
        "docker compose rm -v",
        "rm -rf",
    )
    for token in forbidden:
        assert token not in text


def test_start_uses_docker_compose_up_wait_or_polling_fallback() -> None:
    text = _script_text()

    assert "_compose up -d --wait" in text
    assert "--wait-timeout" in text
    assert "polling fallback" in text
    assert "_wait_service_healthy" in text


def test_stop_uses_compose_stop_not_down() -> None:
    text = _script_text()

    assert "_compose stop" in text
    assert "compose down" not in text


def test_ollama_warmup_and_shutdown_keep_alive_contracts() -> None:
    text = _script_text()

    assert 'export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"' in text
    assert '\\"keep_alive\\":\\"-1\\"' in text
    assert '\\"keep_alive\\":0' in text
    assert "QUIMERA_OLLAMA_AUTO_PULL" not in text
    assert "ollama pull" in text


def test_litellm_and_qdrant_health_contracts() -> None:
    text = _script_text()

    assert "/health/readiness" in text
    assert "/readyz" in text
    assert "/healthz" in text
    assert "fallback /health used" in text


def test_status_table_headers_are_present() -> None:
    text = _script_text()

    assert "SERVIÇO | STATUS | VERSÃO/IMAGEM | PORTA/URL | HEALTH" in text
    assert "_status_table()" in text


def test_postgres_service_detection_order() -> None:
    text = _script_text()

    assert "POSTGRES_SERVICE" in text
    assert '_service_exists "postgres"' in text
    assert '_service_exists "postgres-memory"' in text
    assert "grep -E 'postgres'" in text


def test_star_quimera_wrapper_execs_start_script() -> None:
    assert STAR_WRAPPER.exists()
    text = STAR_WRAPPER.read_text(encoding="utf-8")

    assert 'exec "$(dirname "$0")/start_quimera.sh" "$@"' in text


def test_root_start_quimera_wrapper_execs_canonical_script() -> None:
    text = ROOT_SCRIPT.read_text(encoding="utf-8")

    assert 'exec "$(dirname "$0")/scripts/start_quimera.sh" "$@"' in text


def test_compose_still_does_not_manage_litellm() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "quimera-litellm" not in text
    assert "\n  litellm:" not in text


def _line_containing(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"missing line containing {needle!r}")
