#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/litellm_config.yaml"
RUNTIME_CONFIG_FILE="${SCRIPT_DIR}/generated/litellm_config.runtime.yaml"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
PID_FILE="${RUNTIME_DIR}/litellm.pid"
LOG_DIR="${RUNTIME_DIR}/logs"
LOG_FILE="${LOG_DIR}/litellm.log"
PLACEHOLDER_KEY="quimera-dev-key-change-me"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

wait_readiness() {
  local url="$1"
  local pid="$2"
  for _ in $(seq 1 10); do
    if curl -fsS --max-time 1 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      return 1
    fi
    sleep 1
  done
  return 1
}

litellm_docker_container_running() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  docker ps --filter 'name=^/quimera-litellm$' --format '{{.Names}}' 2>/dev/null | grep -qx 'quimera-litellm'
}

find_litellm_bin() {
  if [[ -n "${LITELLM_BIN:-}" ]]; then
    printf '%s\n' "${LITELLM_BIN}"
    return 0
  fi
  if command -v litellm >/dev/null 2>&1; then
    command -v litellm
    return 0
  fi
  if [[ -x "${SCRIPT_DIR}/.venv/bin/litellm" ]]; then
    printf '%s\n' "${SCRIPT_DIR}/.venv/bin/litellm"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    printf 'uv run litellm\n'
    return 0
  fi
  return 1
}

# Auto-source .env.local from repo root when called standalone.
if [[ -z "${LITELLM_MASTER_KEY:-}" && "${LITELLM_DISABLE_AUTO_ENV:-0}" != "1" ]]; then
  ENV_FILE="${REPO_ROOT}/.env.local"
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
fi

export LITELLM_MODE=PRODUCTION
export LITELLM_LOG=ERROR
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-${OLLAMA_API_BASE:-http://127.0.0.1:11434}}"
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-${OLLAMA_BASE_URL}}"
export QDRANT_API_BASE="${QDRANT_API_BASE:-http://127.0.0.1:6333}"
export QWEN_MODEL="${QWEN_MODEL:-${QUIMERA_OLLAMA_CHAT_MODEL:-qwen3:14b}}"
export EMBED_MODEL="${EMBED_MODEL:-${QUIMERA_OLLAMA_EMBED_MODEL:-nomic-embed-text:latest}}"
export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama_chat/${QWEN_MODEL}}"
export LITELLM_LOCAL_EMBED_MODEL="${LITELLM_LOCAL_EMBED_MODEL:-ollama/${EMBED_MODEL}}"
export LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
export LITELLM_PORT="${LITELLM_PORT:-4000}"
export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://${LITELLM_HOST}:${LITELLM_PORT}}"
export QUIMERA_LITELLM_CONFIG="${QUIMERA_LITELLM_CONFIG:-${CONFIG_FILE}}"
export QUIMERA_LITELLM_RUNTIME_CONFIG="${QUIMERA_LITELLM_RUNTIME_CONFIG:-${RUNTIME_CONFIG_FILE}}"

[[ "${LITELLM_HOST}" == "127.0.0.1" ]] || fail "Refusing to bind LiteLLM to '${LITELLM_HOST}'."
case "${OLLAMA_BASE_URL}" in
  http://127.0.0.1:11434|http://localhost:11434) ;;
  *) fail "OLLAMA_BASE_URL must be local-only. Got '${OLLAMA_BASE_URL}'." ;;
esac
case "${QDRANT_API_BASE}" in
  http://127.0.0.1:6333|http://localhost:6333) ;;
  *) fail "QDRANT_API_BASE must be local-only. Got '${QDRANT_API_BASE}'." ;;
esac
case "${LITELLM_LOCAL_CHAT_MODEL}" in
  ollama/*|ollama_chat/*) ;;
  *) fail "LITELLM_LOCAL_CHAT_MODEL must use the local Ollama provider. Got '${LITELLM_LOCAL_CHAT_MODEL}'." ;;
esac
case "${LITELLM_LOCAL_EMBED_MODEL}" in
  ollama/*) ;;
  *) fail "LITELLM_LOCAL_EMBED_MODEL must use the local Ollama provider. Got '${LITELLM_LOCAL_EMBED_MODEL}'." ;;
esac

if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
  printf 'WARNING: LITELLM_MASTER_KEY is unset; protected endpoints may reject requests.\n' >&2
elif [[ "${LITELLM_MASTER_KEY}" == "${PLACEHOLDER_KEY}" || "${LITELLM_MASTER_KEY}" == "quimera-dev-key" ]]; then
  printf 'WARNING: placeholder LITELLM_MASTER_KEY is in use; rotate it for shared runtimes.\n' >&2
fi

mkdir -p "${RUNTIME_DIR}" "${LOG_DIR}"

if litellm_docker_container_running; then
  fail "Refusing to reuse quimera-litellm Docker container. LiteLLM must run as a host process."
fi

if curl -fsS --max-time 1 "${LITELLM_BASE_URL%/}/health/readiness" >/dev/null 2>&1; then
  printf 'LiteLLM already healthy at %s; reusing existing host process.\n' "${LITELLM_BASE_URL}"
  exit 0
fi

(cd "${REPO_ROOT}" && python -m infra.litellm.config_validator "${QUIMERA_LITELLM_CONFIG}" >/dev/null)
(cd "${REPO_ROOT}" && python -m infra.litellm.render_config --source "${QUIMERA_LITELLM_CONFIG}" --output "${QUIMERA_LITELLM_RUNTIME_CONFIG}" >/dev/null)

LITELLM_CMD="$(find_litellm_bin)" || fail "litellm command not found. Install LiteLLM in the host environment." 127

# shellcheck disable=SC2206
CMD_PARTS=(${LITELLM_CMD})
"${CMD_PARTS[@]}" \
  --config "${QUIMERA_LITELLM_RUNTIME_CONFIG}" \
  --host "${LITELLM_HOST}" \
  --port "${LITELLM_PORT}" \
  --num_workers 1 \
  --telemetry False > "${LOG_FILE}" 2>&1 &
pid="$!"
printf '%s\n' "${pid}" > "${PID_FILE}"

if ! wait_readiness "${LITELLM_BASE_URL%/}/health/readiness" "${pid}"; then
  kill -TERM "${pid}" >/dev/null 2>&1 || true
  rm -f "${PID_FILE}"
  fail "LiteLLM did not become ready within 10s. See ${LOG_FILE}."
fi

printf 'LiteLLM started at %s with PID %s\n' "${LITELLM_BASE_URL}" "${pid}"
