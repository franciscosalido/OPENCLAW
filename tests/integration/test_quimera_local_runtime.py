from __future__ import annotations

import os
import shutil
import subprocess

import httpx
import pytest


pytestmark = pytest.mark.integration
COMPOSE_FILE = "infra/docker/compose.quimera.local.yml"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_quimera_status_reports_when_stack_is_online() -> None:
    if not _docker_available():
        pytest.skip("Docker is unavailable")
    compose_ps = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            COMPOSE_FILE,
            "ps",
            "--status",
            "running",
            "postgres-memory",
            "qdrant",
            "litellm",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if not all(name in compose_ps.stdout for name in ("postgres-memory", "qdrant", "litellm")):
        pytest.skip("quimera local compose stack is not fully online")
    try:
        qdrant = httpx.get("http://127.0.0.1:6333/healthz", timeout=2.0)
        litellm = httpx.get("http://127.0.0.1:4000/health/readiness", timeout=2.0)
        ollama = httpx.get("http://127.0.0.1:11434/api/version", timeout=2.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"local runtime is not fully online: {exc.__class__.__name__}")
    if qdrant.status_code >= 400 or litellm.status_code >= 400 or ollama.status_code >= 400:
        pytest.skip("local runtime is not fully online")

    result = subprocess.run(
        ["./scripts/start_quimera.sh", "status"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


def test_quimera_runtime_control_is_opt_in() -> None:
    if os.environ.get("QUIMERA_TEST_CAN_CONTROL_RUNTIME") != "1":
        pytest.skip("QUIMERA_TEST_CAN_CONTROL_RUNTIME=1 is required")

    result = subprocess.run(
        ["./scripts/start_quimera.sh", "doctor"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
