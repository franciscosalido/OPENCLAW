#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/compose.quimera.local.yml"
OLLAMA_ENV_FILE="${REPO_ROOT}/infra/ollama/ollama_config.env"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
OLLAMA_PID_FILE="${RUNTIME_DIR}/ollama.pid"
# Own Ollama process marker: .runtime/ollama.pid

COMMAND="${1:-start}"
if [[ "${COMMAND}" == --* ]]; then
  case "${COMMAND}" in
    --status) COMMAND="status" ;;
    --stop) COMMAND="stop" ;;
    --smoke) COMMAND="test" ;;
    --help|-h) COMMAND="help" ;;
    *) ;;
  esac
else
  shift || true
fi

BUILD=0
RUN_WARMUP=0
RUN_DOCTOR=0
RUN_INTEGRATION=0
RELEASE_MODELS=0
NO_DOCKER=0
NO_OLLAMA=0
FOLLOW_LOGS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) BUILD=1 ;;
    --warmup) RUN_WARMUP=1 ;;
    --doctor) RUN_DOCTOR=1 ;;
    --integration) RUN_INTEGRATION=1 ;;
    --release-models) RELEASE_MODELS=1 ;;
    --no-docker) NO_DOCKER=1 ;;
    --no-ollama) NO_OLLAMA=1 ;;
    --logs) FOLLOW_LOGS=1 ;;
    --help|-h) COMMAND="help" ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

load_env() {
  if [[ -f "${REPO_ROOT}/.env.local" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env.local"
    set +a
  fi
  if [[ -f "${OLLAMA_ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${OLLAMA_ENV_FILE}"
    set +a
  fi
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
  export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
  export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
  export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"
  export QUIMERA_OLLAMA_EMBED_MODEL="${QUIMERA_OLLAMA_EMBED_MODEL:-nomic-embed-text:latest}"
  export QUIMERA_OLLAMA_CHAT_MODEL="${QUIMERA_OLLAMA_CHAT_MODEL:-qwen3:14b}"
}

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

wait_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "${label} did not become ready at ${url}" >&2
  return 1
}

ensure_runtime_dir() {
  mkdir -p "${RUNTIME_DIR}"
}

ensure_ollama() {
  if [[ "${NO_OLLAMA}" -eq 1 ]]; then
    return 0
  fi
  if curl -fsS --max-time 2 "${OLLAMA_BASE_URL}/api/version" >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is not running and ollama is not in PATH" >&2
    return 1
  fi
  ensure_runtime_dir
  OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE}" \
  OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL}" \
  OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS}" \
    nohup ollama serve > "${RUNTIME_DIR}/ollama.log" 2>&1 &
  echo "$!" > "${OLLAMA_PID_FILE}"
  wait_http "${OLLAMA_BASE_URL}/api/version" "Ollama" 20
}

start_stack() {
  load_env
  ensure_runtime_dir
  ensure_ollama
  if [[ "${NO_DOCKER}" -eq 0 ]]; then
    # The default start path issues docker compose up -d.
    local args=(up -d)
    if [[ "${BUILD}" -eq 1 ]]; then
      args=(up -d --build)
    fi
    compose "${args[@]}"
    wait_http "http://127.0.0.1:6333/healthz" "Qdrant" 30
  fi
  if [[ "${RUN_WARMUP}" -eq 1 ]]; then
    warmup_models
  fi
  if [[ "${RUN_DOCTOR}" -eq 1 ]]; then
    doctor
  fi
  if [[ "${FOLLOW_LOGS}" -eq 1 ]]; then
    logs
  fi
}

stop_stack() {
  load_env
  if [[ "${RELEASE_MODELS}" -eq 1 ]]; then
    release_models || true
  fi
  if [[ "${NO_DOCKER}" -eq 0 ]]; then
    compose down
  fi
  if [[ -f "${OLLAMA_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${OLLAMA_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" || true
    fi
    rm -f "${OLLAMA_PID_FILE}"
  fi
}

status_stack() {
  load_env
  local rc=0
  if command -v docker >/dev/null 2>&1; then
    compose ps || rc=1
    compose exec -T postgres-memory pg_isready -U quimera -d quimera -h 127.0.0.1 || rc=1
  else
    echo "Docker unavailable" >&2
    rc=1
  fi
  curl -fsS --max-time 3 "http://127.0.0.1:6333/healthz" >/dev/null || rc=1
  curl -fsS --max-time 3 "http://127.0.0.1:4000/health/readiness" >/dev/null || rc=1
  curl -fsS --max-time 3 "${OLLAMA_BASE_URL}/api/version" >/dev/null || rc=1
  return "${rc}"
}

logs() {
  compose logs -f --tail=200
}

doctor() {
  load_env
  local rc=0
  command -v docker >/dev/null 2>&1 || { echo "Docker missing" >&2; rc=1; }
  [[ -f "${COMPOSE_FILE}" ]] || { echo "Compose file missing" >&2; rc=1; }
  curl -fsS --max-time 3 "${OLLAMA_BASE_URL}/api/version" >/dev/null || { echo "Ollama unavailable" >&2; rc=1; }
  curl -fsS --max-time 3 "http://127.0.0.1:6333/healthz" >/dev/null || { echo "Qdrant unavailable" >&2; rc=1; }
  curl -fsS --max-time 3 "http://127.0.0.1:4000/health/readiness" >/dev/null || { echo "LiteLLM unavailable" >&2; rc=1; }
  return "${rc}"
}

run_tests() {
  load_env
  export TEST_QDRANT_URL="${TEST_QDRANT_URL:-http://127.0.0.1:6333}"
  export OLLAMA_BASE_URL
  export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://127.0.0.1:4000}"
  export TEST_POSTGRES_DSN="${TEST_POSTGRES_DSN:-postgresql://quimera@127.0.0.1:5432/quimera}"
  uv run pytest \
    tests/unit/test_ollama_tuning.py \
    tests/unit/test_ollama_warmup_contract.py \
    tests/unit/test_start_quimera_script.py
  if [[ "${RUN_INTEGRATION}" -eq 1 ]]; then
    uv run pytest -m integration \
      tests/integration/test_ollama_warmup.py \
      tests/integration/test_quimera_local_runtime.py
  fi
}

warmup_models() {
  load_env
  uv run python "${REPO_ROOT}/infra/ollama/warmup.py"
}

release_models() {
  load_env
  uv run python "${REPO_ROOT}/infra/ollama/shutdown_hook.py"
}

show_help() {
  cat <<'HELP'
Usage: scripts/start_quimera.sh <command> [flags]

Commands: start, stop, restart, status, logs, doctor, test, warmup, release
Flags: --build --warmup --doctor --integration --release-models --no-docker --no-ollama --logs --help
HELP
}

case "${COMMAND}" in
  start) start_stack ;;
  stop) stop_stack ;;
  restart) RELEASE_MODELS=1; stop_stack; BUILD=1; RUN_WARMUP=1; RUN_DOCTOR=1; start_stack ;;
  status) status_stack ;;
  logs) logs ;;
  doctor) doctor ;;
  test) run_tests ;;
  warmup) warmup_models ;;
  release) release_models ;;
  help|--help|-h) show_help ;;
  *) echo "Unknown command: ${COMMAND}" >&2; show_help; exit 2 ;;
esac
