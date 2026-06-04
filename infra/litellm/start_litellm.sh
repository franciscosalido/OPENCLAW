#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/litellm_config.yaml"
RUNTIME_CONFIG_FILE="${SCRIPT_DIR}/generated/litellm_config.runtime.yaml"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

# Auto-source .env.local from repo root when called standalone (start_quimera.sh ja faz isso).
if [ -z "${LITELLM_MASTER_KEY:-}" ] && [ "${LITELLM_DISABLE_AUTO_ENV:-0}" != "1" ]; then
    _ENV="${SCRIPT_DIR}/../../.env.local"
    if [ -f "${_ENV}" ]; then
        set -a && source "${_ENV}" && set +a
    fi
fi

[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY is required. Crie .env.local ou rode via start_quimera.sh."

export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-${OLLAMA_API_BASE:-http://127.0.0.1:11434}}"
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-${OLLAMA_BASE_URL}}"
export QWEN_MODEL="${QWEN_MODEL:-${QUIMERA_OLLAMA_CHAT_MODEL:-qwen3:14b}}"
export EMBED_MODEL="${EMBED_MODEL:-${QUIMERA_OLLAMA_EMBED_MODEL:-nomic-embed-text:latest}}"
export LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
export LITELLM_PORT="${LITELLM_PORT:-4000}"
export QDRANT_API_BASE="${QDRANT_API_BASE:-http://127.0.0.1:6333}"
export QUIMERA_LITELLM_CONFIG="${QUIMERA_LITELLM_CONFIG:-${CONFIG_FILE}}"
export QUIMERA_LITELLM_RUNTIME_CONFIG="${QUIMERA_LITELLM_RUNTIME_CONFIG:-${RUNTIME_CONFIG_FILE}}"

[ "${LITELLM_HOST}" = "127.0.0.1" ] || fail "Refusing to bind LiteLLM to '${LITELLM_HOST}'. Gateway-0 must bind only to 127.0.0.1."

case "${OLLAMA_API_BASE}" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) fail "OLLAMA_API_BASE must be local-only. Got '${OLLAMA_API_BASE}'." ;;
esac

export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama_chat/${QWEN_MODEL}}"
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

(cd "${SCRIPT_DIR}/../.." && python -m infra.litellm.render_config >/dev/null)

printf 'Starting LiteLLM on http://%s:%s using local Ollama at %s\n' "${LITELLM_HOST}" "${LITELLM_PORT}" "${OLLAMA_API_BASE}"
printf 'Config: %s\n' "${QUIMERA_LITELLM_RUNTIME_CONFIG}"

exec litellm --config "${QUIMERA_LITELLM_RUNTIME_CONFIG}" --host "${LITELLM_HOST}" --port "${LITELLM_PORT}"
