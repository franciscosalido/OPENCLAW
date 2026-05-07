#!/usr/bin/env bash
# Bootstrap Python 3.12 + project dependencies in any sandbox or CI environment.
# Safe to run multiple times (idempotent).
#
# Usage:
#   bash scripts/bootstrap_sandbox.sh
#
# After this script completes, use:
#   uv run pytest tests/ -v
#   uv run mypy backend/ --strict
#   uv run pyright backend/
set -euo pipefail

REQUIRED_PYTHON="3.12"
UV_MIN_VERSION="0.4.0"

# 1. Ensure uv is installed.
if ! command -v uv &>/dev/null; then
    echo "[bootstrap] uv not found; installing via official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the remainder of this script
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

UV_VERSION=$(uv --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")
echo "[bootstrap] uv ${UV_VERSION} found at $(command -v uv)"

# 2. Install Python 3.12 via uv (no system packages needed).
echo "[bootstrap] Ensuring Python ${REQUIRED_PYTHON} is available..."
uv python install "${REQUIRED_PYTHON}"

PYTHON_PATH=$(uv python find "${REQUIRED_PYTHON}" 2>/dev/null || echo "")
if [[ -z "$PYTHON_PATH" ]]; then
    echo "[bootstrap] ERROR: Python ${REQUIRED_PYTHON} not found after install." >&2
    exit 1
fi
echo "[bootstrap] Python ${REQUIRED_PYTHON} at ${PYTHON_PATH}"

# 3. Sync project dependencies.
echo "[bootstrap] Syncing project dependencies with Python ${REQUIRED_PYTHON}..."
uv sync --python "${REQUIRED_PYTHON}"

# 4. Verify the environment is usable.
VENV_PYTHON=$(uv run python --version 2>&1)
echo "[bootstrap] Virtual environment Python: ${VENV_PYTHON}"

if [[ "$VENV_PYTHON" != *"3.12"* ]]; then
    echo "[bootstrap] ERROR: Expected Python 3.12 in venv, got: ${VENV_PYTHON}" >&2
    exit 1
fi

echo ""
echo "[bootstrap] Done. Run project commands with:"
echo "  uv run pytest tests/ -v"
echo "  uv run mypy backend/ --strict"
echo "  uv run pyright backend/"
echo "  uv run python scripts/ingest_corpus.py --help"
