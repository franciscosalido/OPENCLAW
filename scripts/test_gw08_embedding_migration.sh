#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${QDRANT_URL:=http://127.0.0.1:6333}"
: "${OLLAMA_API_BASE:=http://127.0.0.1:11434}"
: "${QUIMERA_LLM_BASE_URL:=http://127.0.0.1:4000/v1}"

if [[ -z "${QUIMERA_LLM_API_KEY:-}" ]]; then
  printf 'ERROR: QUIMERA_LLM_API_KEY is required and must match local LITELLM_MASTER_KEY.\n' >&2
  exit 1
fi

require_local_url() {
  local name="$1"
  local value="$2"
  case "$value" in
    http://127.0.0.1:*|http://localhost:*|http://[::1]:*)
      ;;
    *)
      printf 'ERROR: %s must be a local-only HTTP URL, got %s\n' "$name" "$value" >&2
      exit 1
      ;;
  esac
}

require_local_url "QDRANT_URL" "$QDRANT_URL"
require_local_url "OLLAMA_API_BASE" "$OLLAMA_API_BASE"
require_local_url "QUIMERA_LLM_BASE_URL" "$QUIMERA_LLM_BASE_URL"

export QDRANT_URL
export OLLAMA_API_BASE
export QUIMERA_LLM_BASE_URL
export RUN_GW08_EMBEDDING_MIGRATION_SMOKE=1
export RUN_GW08_EMBEDDING_PARITY_SMOKE=1

printf 'GW-08 controlled embedding migration smoke starting (local services only).\n'
printf 'Qdrant=%s LiteLLM=%s Ollama=%s\n' "$QDRANT_URL" "$QUIMERA_LLM_BASE_URL" "$OLLAMA_API_BASE"

cd "$ROOT_DIR"
uv run pytest tests/smoke/test_rag_gateway_embedding_migration_smoke.py -v -s

printf 'GW-08 controlled embedding migration smoke completed.\n'
