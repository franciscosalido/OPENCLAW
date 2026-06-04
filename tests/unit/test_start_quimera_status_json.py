from __future__ import annotations

import json
import subprocess

import pytest

from scripts import quimera_status


def test_start_quimera_status_json_is_parseable() -> None:
    result = subprocess.run(
        ["bash", "scripts/start_quimera.sh", "status", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )

    data = json.loads(result.stdout)
    assert data["schema_version"] == "quimera-status-v1"
    assert "postgres" in data["services"]
    assert "qdrant" in data["services"]
    assert "ollama" in data["services"]
    assert result.stdout.strip().startswith("{")


def test_rag01b_acceptance_json_is_parseable() -> None:
    result = subprocess.run(
        ["bash", "scripts/start_quimera.sh", "rag01b-acceptance", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )

    data = json.loads(result.stdout)
    assert data["schema_version"] == "rag01b-acceptance-v1"
    assert data["adr"] == "accepted"


def test_litellm_docker_container_is_reported_as_host_only_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="quimera-litellm\n", stderr="")

    monkeypatch.setattr("scripts.quimera_status.subprocess.run", fake_run)

    assert quimera_status._litellm_docker_container_running() is True
