#!/usr/bin/env bash
# Emit clean Pyright JSON by warming Pyright before the JSON-producing command.
set -euo pipefail

REPO_ROOT="${QUIMERA_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"

if command -v pyright >/dev/null 2>&1; then
    PYRIGHT_CMD=(pyright)
elif command -v uv >/dev/null 2>&1; then
    PYRIGHT_CMD=(uv run pyright)
else
    echo "[vibe-pyright] pyright or uv is required" >&2
    exit 127
fi

"${PYRIGHT_CMD[@]}" --version >/dev/null
"${PYRIGHT_CMD[@]}" --outputjson "$@"
