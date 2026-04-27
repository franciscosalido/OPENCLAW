#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/litellm_config.yaml"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY is required. Export a local dev key before starting LiteLLM."

export OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
export QWEN_MODEL="${QWEN_MODEL:-qwen3:14b}"
export EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
export LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
export LITELLM_PORT="${LITELLM_PORT:-4000}"

[ "${LITELLM_HOST}" = "127.0.0.1" ] || fail "Refusing to bind LiteLLM to '${LITELLM_HOST}'. Gateway-0 must bind only to 127.0.0.1."

case "${OLLAMA_API_BASE}" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) fail "OLLAMA_API_BASE must be local-only. Got '${OLLAMA_API_BASE}'." ;;
esac

export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama/${QWEN_MODEL}}"
export LITELLM_LOCAL_EMBED_MODEL="${LITELLM_LOCAL_EMBED_MODEL:-ollama/${EMBED_MODEL}}"

case "${LITELLM_LOCAL_CHAT_MODEL}" in
  ollama/*|ollama_chat/*) ;;
  *) fail "LITELLM_LOCAL_CHAT_MODEL must use the local Ollama provider. Got '${LITELLM_LOCAL_CHAT_MODEL}'." ;;
esac

case "${LITELLM_LOCAL_EMBED_MODEL}" in
  ollama/*) ;;
  *) fail "LITELLM_LOCAL_EMBED_MODEL must use the local Ollama provider. Got '${LITELLM_LOCAL_EMBED_MODEL}'." ;;
esac

command -v litellm >/dev/null 2>&1 || fail "litellm command not found. Run: cd infra/litellm && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" 127

printf 'Starting LiteLLM on http://%s:%s using local Ollama at %s\n' "${LITELLM_HOST}" "${LITELLM_PORT}" "${OLLAMA_API_BASE}"
printf 'Config: %s\n' "${CONFIG_FILE}"

exec litellm --config "${CONFIG_FILE}" --host "${LITELLM_HOST}" --port "${LITELLM_PORT}"
