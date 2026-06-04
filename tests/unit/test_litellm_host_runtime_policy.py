from __future__ import annotations

from pathlib import Path


COMPOSE = Path("infra/docker/compose.quimera.local.yml")
SCRIPT = Path("scripts/start_quimera.sh")
START_LITELLM = Path("infra/litellm/start_litellm.sh")
GENERATED = Path("infra/litellm/generated")
GITIGNORE = Path(".gitignore")


def test_generated_runtime_directory_is_versioned_only_with_gitkeep() -> None:
    assert (GENERATED / ".gitkeep").exists()
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    assert "infra/litellm/generated/*" in gitignore
    assert "!infra/litellm/generated/" in gitignore
    assert "!infra/litellm/generated/.gitkeep" in gitignore


def test_compose_only_manages_postgres_and_qdrant() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "postgres-memory:" in text
    assert "qdrant:" in text
    assert "litellm:" not in text
    assert "4000:4000" not in text


def test_start_script_runs_litellm_as_host_process() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    start_text = START_LITELLM.read_text(encoding="utf-8")

    assert "--host" in start_text
    assert "127.0.0.1" in start_text
    assert "--port" in start_text
    assert "4000" in start_text
    assert "docker compose" in text
    assert "compose exec -T litellm" not in text
