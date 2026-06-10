from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile.openclaw-sandbox"
PYPROJECT = REPO_ROOT / "pyproject.toml"
BOOTSTRAP = REPO_ROOT / "scripts" / "vibe_sandbox_bootstrap.sh"
SEMGREP = REPO_ROOT / "scripts" / "vibe_semgrep_scan.sh"
PYRIGHT_JSON = REPO_ROOT / "scripts" / "vibe_pyright_json.sh"
VIBE_DEEP_RUN = REPO_ROOT / "scripts" / "vibe_deep_run.sh"
QUARANTINE_VENV = REPO_ROOT / "scripts" / "quarantine_venv_to_patio.sh"
GITIGNORE = REPO_ROOT / ".gitignore"


def test_vibe_sandbox_bootstrap_installs_project_editable_after_mount() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert 'REPO_ROOT="${1:-${QUIMERA_REPO_ROOT:-/workspace}}"' in text
    assert 'PYTHON_BIN="${PYTHON}"' in text
    assert 'PYTHON_BIN="python3"' in text
    assert "uv pip install --no-deps --editable ." in text
    assert '"${PYTHON_BIN}" -m pip install --no-deps --editable .' in text
    assert 'importlib.import_module("backend")' in text


def test_vibe_semgrep_is_isolated_from_project_opentelemetry_dependencies() -> None:
    script = SEMGREP.read_text(encoding="utf-8")
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    assert "semgrep/semgrep:latest" in script
    assert "uvx semgrep" in script
    assert "pip install semgrep" not in script
    assert "opentelemetry-sdk>=1.42.1" in pyproject
    assert "semgrep" not in pyproject


def test_vibe_pyright_json_warms_runtime_before_outputjson() -> None:
    text = PYRIGHT_JSON.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "--version >/dev/null" in text
    assert "--outputjson" in text
    assert text.index("--version >/dev/null") < text.index("--outputjson")


def test_openclaw_sandbox_prewarms_pyright_and_uses_nodejs() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG PYTHON_IMAGE=python:3.12-slim@sha256:" in text
    assert "FROM ${PYTHON_IMAGE}" in text
    assert "sys.version_info[:2] == (3, 12)" in text
    assert "FROM python:3.14" not in text
    assert "nodejs" in text
    assert "nodejs npm" not in text
    assert "UV_PROJECT_ENVIRONMENT=/opt/openclaw-venv uv sync --frozen" in text
    assert "/opt/openclaw-venv/bin/pyright --version >/dev/null" in text
    assert "mv .venv /opt/openclaw-venv" not in text
    assert "postgresql-client-18" in text


def test_vibe_deep_runner_rebuilds_py312_image_and_joins_quimera_network() -> None:
    text = VIBE_DEEP_RUN.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "vibe-sandbox:py312" in text
    assert 'docker build --pull -f "${DOCKERFILE}"' in text
    assert "quimera_network" in text
    assert "quimera-local_default" in text
    assert '--network "${network_name}"' in text
    assert "quimera-postgres-memory" in text
    assert "quimera-qdrant" in text
    assert "QUIMERA_E2E=true" in text
    assert "RUN_AGENT0_E2E" in text
    assert "tests/e2e" in text
    assert "TEST_POSTGRES_DSN" in text
    assert "host.docker.internal" in text
    assert "bash -c" in text
    assert 'export PATH="${VIRTUAL_ENV}/bin:${PATH}"' in text
    assert "printf ${TEST_POSTGRES_DSN}" not in text
    assert "echo ${TEST_POSTGRES_DSN}" not in text


def test_mutmut_config_copies_context_without_symlinked_mutants_dir() -> None:
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    gitignore = GITIGNORE.read_text(encoding="utf-8")

    assert "[tool.mutmut]" in pyproject
    assert 'source_paths = ["backend"]' in pyproject
    assert "paths_to_mutate" not in pyproject
    assert "mutate_only_covered_lines = false" in pyproject
    for required in ('"config"', '"infra"', '"integration"', '"scripts"', '"tests"'):
        assert required in pyproject
    assert ".mutmut-cache/" in gitignore
    assert "mutants/" in gitignore


def test_vibe_patio_quarantine_script_is_reversible_and_narrow() -> None:
    text = QUARANTINE_VENV.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "/Users/fas/projetos/_patio_venvs" in text
    assert "rm -rf" not in text
    assert 'mv "${source_path}" "${target}"' in text
    assert "Refusing to move non-venv path" in text
