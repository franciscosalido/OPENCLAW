#!/usr/bin/env bash
# Runtime bootstrap for the Vibe sandbox after the repository is mounted.
set -euo pipefail

REPO_ROOT="${1:-${QUIMERA_REPO_ROOT:-/workspace}}"
cd "${REPO_ROOT}"

if [[ -n "${PYTHON:-}" ]]; then
    PYTHON_BIN="${PYTHON}"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "[vibe-bootstrap] python or python3 is required" >&2
    exit 127
fi

if [[ ! -f pyproject.toml ]]; then
    echo "[vibe-bootstrap] pyproject.toml not found at ${REPO_ROOT}" >&2
    exit 2
fi

if command -v uv >/dev/null 2>&1; then
    uv pip install --no-deps --editable .
else
    "${PYTHON_BIN}" -m pip install --no-deps --editable .
fi

"${PYTHON_BIN}" - <<'PY'
import importlib

importlib.import_module("backend")
PY
