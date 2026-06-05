#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/compose.quimera.local.yml"
OLLAMA_ENV_FILE="${REPO_ROOT}/infra/ollama/ollama_config.env"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
OLLAMA_PID_FILE="${RUNTIME_DIR}/ollama.pid"
LITELLM_PID_FILE="${RUNTIME_DIR}/litellm.pid"
LITELLM_LOG_FILE="${RUNTIME_DIR}/logs/litellm.log"
LITELLM_CONFIG_FILE="${REPO_ROOT}/infra/litellm/litellm_config.yaml"
LITELLM_RUNTIME_CONFIG_FILE="${REPO_ROOT}/infra/litellm/generated/litellm_config.runtime.yaml"
QUIMERA_DEV_LITELLM_PLACEHOLDER_KEY="quimera-dev-key-change-me"
# Own Ollama process marker: .runtime/ollama.pid
# Own LiteLLM process marker: .runtime/litellm.pid

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
OTEL_JSON=0
STATUS_JSON=0

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
    --json) OTEL_JSON=1; STATUS_JSON=1 ;;
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
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-${OLLAMA_API_BASE:-http://127.0.0.1:11434}}"
  export OLLAMA_API_BASE="${OLLAMA_API_BASE:-${OLLAMA_BASE_URL}}"
  export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
  export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
  export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"
  export QUIMERA_OLLAMA_EMBED_MODEL="${QUIMERA_OLLAMA_EMBED_MODEL:-nomic-embed-text:latest}"
  export QUIMERA_OLLAMA_CHAT_MODEL="${QUIMERA_OLLAMA_CHAT_MODEL:-qwen3:14b}"
  export QWEN_MODEL="${QWEN_MODEL:-${QUIMERA_OLLAMA_CHAT_MODEL}}"
  export EMBED_MODEL="${EMBED_MODEL:-${QUIMERA_OLLAMA_EMBED_MODEL}}"
  export LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
  export LITELLM_PORT="${LITELLM_PORT:-4000}"
  export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://${LITELLM_HOST}:${LITELLM_PORT}}"
  export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama_chat/${QWEN_MODEL}}"
  export LITELLM_LOCAL_EMBED_MODEL="${LITELLM_LOCAL_EMBED_MODEL:-ollama/${EMBED_MODEL}}"
  export QDRANT_API_BASE="${QDRANT_API_BASE:-http://127.0.0.1:6333}"
  export QUIMERA_LITELLM_CONFIG="${QUIMERA_LITELLM_CONFIG:-${LITELLM_CONFIG_FILE}}"
  export QUIMERA_LITELLM_RUNTIME_CONFIG="${QUIMERA_LITELLM_RUNTIME_CONFIG:-${LITELLM_RUNTIME_CONFIG_FILE}}"
}

compose() {
  local env_file="${REPO_ROOT}/.env.local"
  if [[ -f "${env_file}" ]]; then
    docker compose --env-file="${env_file}" -f "${COMPOSE_FILE}" "$@"
  else
    docker compose -f "${COMPOSE_FILE}" "$@"
  fi
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

litellm_readiness_ok() {
  curl -fsS --max-time 2 "${LITELLM_BASE_URL%/}/health/readiness" >/dev/null 2>&1
}

litellm_validate() {
  load_env
  uv run python -m infra.litellm.config_validator "${QUIMERA_LITELLM_CONFIG}"
}

litellm_render() {
  load_env
  uv run python -m infra.litellm.render_config
}

litellm_smoke() {
  load_env
  uv run python -m infra.litellm.smoke_test
}

litellm_audit() {
  load_env
  uv run python -m infra.litellm.audit \
    --json "${RUNTIME_DIR}/reports/litellm_audit.json" \
    --markdown "${RUNTIME_DIR}/reports/litellm_audit.md"
}

litellm_fingerprint() {
  load_env
  uv run python -m infra.litellm.version_fingerprint
}

litellm_benchmark() {
  load_env
  uv run python -m infra.litellm.overhead_benchmark
}

otel_doctor() {
  load_env
  if [[ "${OTEL_JSON}" -eq 1 ]]; then
    uv run python -m backend.observability.tracer --doctor --json --config "${QUIMERA_LITELLM_CONFIG}"
  else
    uv run python -m backend.observability.tracer --doctor --config "${QUIMERA_LITELLM_CONFIG}"
  fi
}

litellm_start() {
  load_env
  ensure_runtime_dir
  bash "${REPO_ROOT}/infra/litellm/start_litellm.sh"
}

litellm_stop() {
  load_env
  if [[ ! -f "${LITELLM_PID_FILE}" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "${LITELLM_PID_FILE}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill -TERM "${pid}" || true
    for _ in $(seq 1 10); do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if kill -0 "${pid}" >/dev/null 2>&1; then
      echo "LiteLLM PID ${pid} did not stop after SIGTERM; sending SIGKILL to owned PID." >&2
      kill -KILL "${pid}" || true
    fi
  fi
  rm -f "${LITELLM_PID_FILE}"
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
  litellm_start
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
  litellm_stop
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
  if [[ "${STATUS_JSON}" -eq 1 ]]; then
    uv run python "${REPO_ROOT}/scripts/quimera_status.py" status --json
    return $?
  fi
  local rc=0
  if command -v docker >/dev/null 2>&1; then
    compose ps || rc=1
    compose exec -T postgres-memory pg_isready -U quimera -d quimera -h 127.0.0.1 || rc=1
  else
    echo "Docker unavailable" >&2
    rc=1
  fi
  curl -fsS --max-time 3 "${QDRANT_API_BASE%/}/healthz" >/dev/null || rc=1
  litellm_readiness_ok || rc=1
  curl -fsS --max-time 3 "${OLLAMA_BASE_URL}/api/version" >/dev/null || rc=1
  return "${rc}"
}

rag01b_acceptance() {
  load_env
  if [[ "${STATUS_JSON}" -eq 1 ]]; then
    uv run python "${REPO_ROOT}/scripts/quimera_status.py" rag01b-acceptance --json
  else
    uv run python "${REPO_ROOT}/scripts/quimera_status.py" rag01b-acceptance
  fi
}

integration_health() {
  load_env
  if [[ "${STATUS_JSON}" -eq 1 ]]; then
    uv run python -m integration.check_integration_health --json --write-artifact
  else
    uv run python -m integration.check_integration_health --write-artifact
  fi
}

mcp_status() {
  load_env
  uv run python -m integration.check_integration_health --json --write-artifact
}

agentic0_smoke() {
  load_env
  if [[ "${STATUS_JSON}" -eq 1 ]]; then
    uv run python -m integration.run_agentic0_smoke_test --json
  else
    uv run python -m integration.run_agentic0_smoke_test
  fi
}

pr08_report() {
  load_env
  uv run python -m integration.run_agentic0_smoke_test --allow-degraded >/dev/null
  printf 'PR-08 report: %s\n' "${REPO_ROOT}/docs/rag/rag_01b_pr08_integration_report.md"
}

rag01b_final_gate() {
  load_env
  local tmp_dir
  local status_file
  local health_file
  local smoke_file
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' RETURN
  status_file="${tmp_dir}/status.json"
  health_file="${tmp_dir}/integration_health.json"
  smoke_file="${tmp_dir}/agentic0_smoke.json"
  uv run python "${REPO_ROOT}/scripts/quimera_status.py" status --json >"${status_file}" || true
  uv run python -m integration.check_integration_health --json --write-artifact >"${health_file}" || true
  uv run python -m integration.run_agentic0_smoke_test --json --allow-degraded >"${smoke_file}" || true
  if [[ "${STATUS_JSON}" -eq 1 ]]; then
    uv run python - "${status_file}" "${health_file}" "${smoke_file}" <<'PY'
import json
import sys

def load_json(path: str) -> dict:
    try:
        content = open(path, encoding="utf-8").read().strip()
    except OSError:
        return {}
    if not content:
        return {}
    try:
        parsed = json.loads(content)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}

report = {
    "schema_version": "rag01b-final-gate-v1",
    "status": load_json(sys.argv[1]),
    "integration_health": load_json(sys.argv[2]),
    "agentic0_smoke": load_json(sys.argv[3]),
}
report["overall"] = "ok" if report["integration_health"].get("overall") in {"ok", "degraded"} else "degraded"
print(json.dumps(report, sort_keys=True))
PY
  else
    printf 'rag01b-final-gate completed\n'
  fi
}

logs() {
  compose logs -f --tail=200
}

doctor() {
  load_env
  local rc=0
  command -v docker >/dev/null 2>&1 || { echo "Docker missing" >&2; rc=1; }
  [[ -f "${COMPOSE_FILE}" ]] || { echo "Compose file missing" >&2; rc=1; }
  if command -v docker >/dev/null 2>&1 && [[ -f "${COMPOSE_FILE}" ]]; then
    if compose config --services | grep -qx "litellm"; then
      echo "Compose must not manage LiteLLM" >&2
      rc=1
    fi
  fi
  curl -fsS --max-time 3 "${OLLAMA_BASE_URL}/api/version" >/dev/null || { echo "Ollama unavailable" >&2; rc=1; }
  curl -fsS --max-time 3 "${QDRANT_API_BASE%/}/healthz" >/dev/null || { echo "Qdrant unavailable" >&2; rc=1; }
  litellm_readiness_ok || { echo "LiteLLM unavailable" >&2; rc=1; }
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
    tests/unit/test_start_quimera_script.py \
    tests/unit/test_litellm_config_validator.py \
    tests/unit/test_litellm_config_yaml.py \
    tests/unit/test_litellm_cache_policy.py \
    tests/unit/test_litellm_timeout_policy.py \
    tests/unit/test_litellm_host_runtime_policy.py \
    tests/unit/test_litellm_audit_contract.py \
    tests/unit/test_litellm_version_fingerprint.py \
    tests/unit/test_litellm_overhead_contract.py \
    tests/unit/test_start_quimera_litellm_host.py
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

Commands: start, stop, restart, status, logs, doctor, test, warmup, release,
          litellm-validate, litellm-render, litellm-start, litellm-stop,
          litellm-restart, litellm-smoke, litellm-audit, litellm-fingerprint,
          litellm-benchmark, otel-doctor, rag01b-acceptance, mcp-status,
          integration-health, agentic0-smoke, pr08-report, rag01b-final-gate
Flags: --build --warmup --doctor --integration --release-models --no-docker --no-ollama --logs --json --help
HELP
}

case "${COMMAND}" in
  start) start_stack ;;
  stop) stop_stack ;;
  restart) RELEASE_MODELS=1; stop_stack; BUILD=1; RUN_WARMUP=1; RUN_DOCTOR=1; start_stack ;;
  status) status_stack ;;
  rag01b-acceptance) rag01b_acceptance ;;
  integration-health) integration_health ;;
  mcp-status) mcp_status ;;
  agentic0-smoke) agentic0_smoke ;;
  pr08-report) pr08_report ;;
  rag01b-final-gate) rag01b_final_gate ;;
  logs) logs ;;
  doctor) doctor ;;
  test) run_tests ;;
  warmup) warmup_models ;;
  release) release_models ;;
  litellm-validate) litellm_validate ;;
  litellm-render) litellm_render ;;
  litellm-start) litellm_start ;;
  litellm-stop) litellm_stop ;;
  litellm-restart) litellm_stop; litellm_start ;;
  litellm-smoke) litellm_smoke ;;
  litellm-audit) litellm_audit ;;
  litellm-fingerprint) litellm_fingerprint ;;
  litellm-benchmark) litellm_benchmark ;;
  otel-doctor) otel_doctor ;;
  help|--help|-h) show_help ;;
  *) echo "Unknown command: ${COMMAND}" >&2; show_help; exit 2 ;;
esac
