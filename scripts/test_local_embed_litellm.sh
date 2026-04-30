#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

[ -n "${QUIMERA_LLM_API_KEY:-}" ] || fail "QUIMERA_LLM_API_KEY is required and should match LITELLM_MASTER_KEY."

QUIMERA_LLM_BASE_URL="${QUIMERA_LLM_BASE_URL:-http://127.0.0.1:4000/v1}"
QUIMERA_LLM_EMBED_MODEL="${QUIMERA_LLM_EMBED_MODEL:-local_embed}"

case "${QUIMERA_LLM_BASE_URL}" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) fail "QUIMERA_LLM_BASE_URL must point to the local LiteLLM gateway. Got '${QUIMERA_LLM_BASE_URL}'." ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || fail "python is required." 127

"${PYTHON_BIN}" - <<'PY'
import asyncio
import os
import sys
import time
from urllib.parse import urlparse

from backend.gateway.embed_client import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    GatewayEmbedClient,
)


SYNTHETIC_TEXT = "Texto sintetico para validar local_embed."


def host(base_url: str) -> str:
    return urlparse(base_url).netloc or "unknown"


async def main() -> None:
    start = time.perf_counter()
    try:
        async with GatewayEmbedClient() as client:
            vector = await client.embed(SYNTHETIC_TEXT)
    except Exception as exc:
        raise SystemExit(f"ERROR: local_embed failed: {exc}") from exc

    elapsed = time.perf_counter() - start
    if len(vector) != DEFAULT_EMBEDDING_DIMENSIONS:
        raise SystemExit(
            "ERROR: local_embed returned "
            f"{len(vector)} dimensions; expected {DEFAULT_EMBEDDING_DIMENSIONS}"
        )
    sys.stdout.write(
        "OK: alias="
        f"{os.environ.get('QUIMERA_LLM_EMBED_MODEL', 'local_embed')} "
        f"host={host(os.environ.get('QUIMERA_LLM_BASE_URL', 'http://127.0.0.1:4000/v1'))} "
        f"dims={len(vector)} elapsed_s={elapsed:.2f}\n"
    )


asyncio.run(main())
PY
