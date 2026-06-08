from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile.openclaw-sandbox"
PYPROJECT = REPO_ROOT / "pyproject.toml"
BOOTSTRAP = REPO_ROOT / "scripts" / "vibe_sandbox_bootstrap.sh"
SEMGREP = REPO_ROOT / "scripts" / "vibe_semgrep_scan.sh"
PYRIGHT_JSON = REPO_ROOT / "scripts" / "vibe_pyright_json.sh"


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

    assert "nodejs" in text
    assert "nodejs npm" not in text
    assert "UV_PROJECT_ENVIRONMENT=/opt/openclaw-venv uv sync --frozen" in text
    assert "/opt/openclaw-venv/bin/pyright --version >/dev/null" in text
    assert "mv .venv /opt/openclaw-venv" not in text
    assert "postgresql-client-18" in text
