#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/litellm_config.yaml"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

command -v curl >/dev/null 2>&1 || fail "curl is required." 127

[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY is required."

LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
LITELLM_PORT="${LITELLM_PORT:-4000}"
OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"

[ "${LITELLM_HOST}" = "127.0.0.1" ] || fail "Refusing non-local LiteLLM host '${LITELLM_HOST}'."

case "${OLLAMA_API_BASE}" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) fail "OLLAMA_API_BASE must be local-only. Got '${OLLAMA_API_BASE}'." ;;
esac

# Strip full-line YAML comments before scanning for remote provider markers.
# sed is used instead of a grep -v pipe so the stripped content can be reused
# across multiple checks without re-reading the file.
# LITELLM_MASTER_KEY and QUIMERA_LLM_API_KEY are local proxy credentials —
# they are not remote provider keys and must not be rejected.
ACTIVE_CONFIG="$(sed '/^[[:space:]]*#/d' "${CONFIG_FILE}")"

# Reject provider-specific remote API key env markers.
if printf '%s\n' "${ACTIVE_CONFIG}" | grep -Eiq \
    'OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY|XAI_API_KEY|AZURE_API_KEY'; then
  fail "Remote provider API key env marker found in active LiteLLM config."
fi

# Reject active remote model provider prefixes.
if printf '%s\n' "${ACTIVE_CONFIG}" | grep -Eiq \
    'model:[[:space:]]*(openai|anthropic|gemini|google|openrouter|xai|azure)/'; then
  fail "Remote provider model found in active LiteLLM config."
fi

if ! curl -fsS --max-time 5 "${OLLAMA_API_BASE%/}/api/tags" >/dev/null; then
  fail "Ollama is not reachable at ${OLLAMA_API_BASE}. Start Ollama and pull local models."
fi

"${SCRIPT_DIR}/test_models.sh"
"${SCRIPT_DIR}/test_local_chat.sh"

printf 'OK: LiteLLM local gateway healthcheck passed.\n'
