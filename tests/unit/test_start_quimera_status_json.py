from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import quimera_status

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_status_helper(command: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/quimera_status.py"), command, "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=env,
    )


def test_start_quimera_status_json_is_parseable() -> None:
    result = _run_status_helper("status")

    data = json.loads(result.stdout)
    assert data["schema_version"] == "quimera-status-v1"
    assert "postgres" in data["services"]
    assert "qdrant" in data["services"]
    assert "ollama" in data["services"]
    assert result.stdout.strip().startswith("{")


def test_rag01b_acceptance_json_is_parseable() -> None:
    result = _run_status_helper("rag01b-acceptance")

    data = json.loads(result.stdout)
    assert data["schema_version"] == "rag01b-acceptance-v1"
    assert data["adr"] == "accepted"


def test_litellm_docker_container_is_reported_as_host_only_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="quimera-litellm\n", stderr="")

    monkeypatch.setattr("scripts.quimera_status.subprocess.run", fake_run)

    assert quimera_status._litellm_docker_container_running() is True
