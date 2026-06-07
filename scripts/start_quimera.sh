#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_COMPOSE_FILE="${REPO_ROOT}/infra/docker/compose.quimera.local.yml"
OLLAMA_ENV_FILE="${REPO_ROOT}/infra/ollama/ollama_config.env"
RUNTIME_DIR="${REPO_ROOT}/.runtime"

COMPOSE_FILE="${QUIMERA_COMPOSE_FILE:-${DEFAULT_COMPOSE_FILE}}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-}"
QDRANT_SERVICE="${QDRANT_SERVICE:-}"

_log() {
  printf '[quimera] %s\n' "$*"
}

_warn() {
  printf '[quimera][warn] %s\n' "$*" >&2
}

_err() {
  printf '[quimera][error] %s\n' "$*" >&2
}

_die() {
  _err "$*"
  exit 1
}

_usage() {
  cat <<'HELP'
Usage:
  ./start_quimera.sh --start
  ./start_quimera.sh --stop
  ./start_quimera.sh --status
HELP
}

_load_env() {
  local file
  for file in "${REPO_ROOT}/.env.local" "${OLLAMA_ENV_FILE}"; do
    if [[ -f "${file}" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "${file}"
      set +a
    fi
  done

  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-${OLLAMA_API_BASE:-http://127.0.0.1:11434}}"
  export OLLAMA_API_BASE="${OLLAMA_API_BASE:-${OLLAMA_BASE_URL}}"
  export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
  export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"
  export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
  export QUIMERA_OLLAMA_CHAT_MODEL="${QUIMERA_OLLAMA_CHAT_MODEL:-qwen3:14b}"
  export QUIMERA_OLLAMA_EMBED_MODEL="${QUIMERA_OLLAMA_EMBED_MODEL:-nomic-embed-text:latest}"
  export QDRANT_API_BASE="${QDRANT_API_BASE:-http://127.0.0.1:6333}"
  export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://127.0.0.1:4000}"
  export QUIMERA_WAIT_TIMEOUT="${QUIMERA_WAIT_TIMEOUT:-90}"
}

_detect_compose_file() {
  [[ -f "${COMPOSE_FILE}" ]] || _die "Compose file not found: ${COMPOSE_FILE}"
  printf '%s\n' "${COMPOSE_FILE}"
}

_compose() {
  docker compose -f "$(_detect_compose_file)" "$@"
}

_service_exists() {
  local service="$1"
  _compose config --services | grep -qx "${service}"
}

_service_container_id() {
  local service="$1"
  _compose ps -q "${service}" 2>/dev/null || true
}

_service_image_current() {
  local container_id="$1"
  [[ -n "${container_id}" ]] || return 0
  docker inspect -f '{{.Config.Image}}' "${container_id}" 2>/dev/null || true
}

_service_image_id_current() {
  local container_id="$1"
  [[ -n "${container_id}" ]] || return 0
  docker inspect -f '{{.Image}}' "${container_id}" 2>/dev/null || true
}

_service_image_expected() {
  local service="$1"
  if [[ "${service}" == "${POSTGRES_SERVICE}" && -n "${IMAGE_POSTGRES:-}" ]]; then
    printf '%s\n' "${IMAGE_POSTGRES}"
    return 0
  fi
  _compose config --format json | python3 -c '
import json
import sys

service = sys.argv[1]
data = json.load(sys.stdin)
services = data.get("services", {})
entry = services.get(service, {})
image = entry.get("image", "")
if image:
    print(image)
' "${service}"
}

_service_config_hash_current() {
  local container_id="$1"
  [[ -n "${container_id}" ]] || return 0
  docker inspect -f '{{ index .Config.Labels "com.docker.compose.config-hash" }}' "${container_id}" 2>/dev/null || true
}

_service_config_hash_expected() {
  local service="$1"
  _compose config --hash "${service}" 2>/dev/null || true
}

_service_has_build() {
  local service="$1"
  _compose config --format json | python3 -c '
import json
import sys

service = sys.argv[1]
data = json.load(sys.stdin)
entry = data.get("services", {}).get(service, {})
sys.exit(0 if entry.get("build") else 1)
' "${service}"
}

_wait_service_healthy() {
  local service="$1"
  local timeout="${2:-${QUIMERA_WAIT_TIMEOUT:-90}}"
  local container_id
  local state
  local health

  for _ in $(seq 1 "${timeout}"); do
    container_id="$(_service_container_id "${service}")"
    if [[ -n "${container_id}" ]]; then
      state="$(docker inspect -f '{{.State.Status}}' "${container_id}" 2>/dev/null || true)"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}" 2>/dev/null || true)"
      if [[ "${state}" == "running" && ( "${health}" == "healthy" || "${health}" == "none" ) ]]; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

_wait_http_200() {
  local url="$1"
  local label="${2:-http}"
  local timeout="${3:-30}"

  for _ in $(seq 1 "${timeout}"); do
    if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  _warn "${label} did not become ready at ${url}"
  return 1
}

_check_docker() {
  _docker_available || _die "Docker is not available"
}

_docker_available() {
  command -v docker >/dev/null 2>&1 || return 1
  docker info >/dev/null 2>&1 || return 1
  _compose config >/dev/null 2>&1 || return 1
}

_detect_postgres_service() {
  if [[ -n "${POSTGRES_SERVICE}" ]]; then
    _service_exists "${POSTGRES_SERVICE}" || _die "POSTGRES_SERVICE does not exist: ${POSTGRES_SERVICE}"
    printf '%s\n' "${POSTGRES_SERVICE}"
    return 0
  fi
  if _service_exists "postgres"; then
    printf 'postgres\n'
    return 0
  fi
  if _service_exists "postgres-memory"; then
    printf 'postgres-memory\n'
    return 0
  fi
  _compose config --services | grep -E 'postgres' | head -n 1 || true
}

_detect_qdrant_service() {
  if [[ -n "${QDRANT_SERVICE}" ]]; then
    _service_exists "${QDRANT_SERVICE}" || _die "QDRANT_SERVICE does not exist: ${QDRANT_SERVICE}"
    printf '%s\n' "${QDRANT_SERVICE}"
    return 0
  fi
  if _service_exists "qdrant"; then
    printf 'qdrant\n'
    return 0
  fi
  _compose config --services | grep -E 'qdrant' | head -n 1 || true
}

_detect_litellm_runtime() {
  if _service_exists "litellm"; then
    printf 'docker\n'
  else
    printf 'host\n'
  fi
}

_detect_ollama_runtime() {
  if _service_exists "ollama"; then
    printf 'docker\n'
  else
    printf 'host\n'
  fi
}

_rebuild_postgres_if_needed() {
  POSTGRES_SERVICE="$(_detect_postgres_service)"
  [[ -n "${POSTGRES_SERVICE}" ]] || _die "Postgres service not found in compose"

  local container_id
  local current_image
  local current_image_id
  local expected_image
  local current_hash
  local expected_hash
  local drift=0

  container_id="$(_service_container_id "${POSTGRES_SERVICE}")"
  if [[ -z "${container_id}" ]]; then
    _log "Postgres container is not running yet"
    return 0
  fi

  current_image="$(_service_image_current "${container_id}")"
  current_image_id="$(_service_image_id_current "${container_id}")"
  expected_image="$(_service_image_expected "${POSTGRES_SERVICE}")"
  current_hash="$(_service_config_hash_current "${container_id}")"
  expected_hash="$(_service_config_hash_expected "${POSTGRES_SERVICE}")"

  if [[ -n "${expected_image}" && "${current_image}" != "${expected_image}" ]]; then
    drift=1
  fi
  if [[ -n "${expected_hash}" && -n "${current_hash}" && "${current_hash}" != "${expected_hash}" ]]; then
    drift=1
  fi
  if [[ -n "${IMAGE_POSTGRES:-}" && "${current_image}" != "${IMAGE_POSTGRES}" ]]; then
    drift=1
  fi

  if [[ "${drift}" -eq 0 ]]; then
    _log "Postgres image up-to-date"
    return 0
  fi

  printf '⚠️  POSTGRES REBUILD DETECTADO\n'
  printf '   Serviço: %s\n' "${POSTGRES_SERVICE}"
  printf '   Container atual: %s\n' "${container_id}"
  printf '   Imagem atual: %s\n' "${current_image:-unknown}"
  printf '   Image ID atual: %s\n' "${current_image_id:-unknown}"
  printf '   Imagem esperada: %s\n' "${expected_image:-build-config}"
  printf '   Volume de dados SERÁ PRESERVADO\n'
  printf '   Nenhum %s %s será executado\n' "docker volume" "rm"
  printf '   Confirmar rebuild? [s/N] '
  read -r confirm

  if [[ "${confirm}" != "s" && "${confirm}" != "S" ]]; then
    _log "Rebuild Postgres cancelado pelo operador"
    exit 0
  fi

  if _service_has_build "${POSTGRES_SERVICE}"; then
    _compose build "${POSTGRES_SERVICE}"
  else
    _compose pull "${POSTGRES_SERVICE}"
  fi
  _compose stop "${POSTGRES_SERVICE}"
  _compose rm -f "${POSTGRES_SERVICE}"
  _compose up -d "${POSTGRES_SERVICE}"
  _wait_service_healthy "${POSTGRES_SERVICE}" || _die "Postgres did not become healthy after rebuild"
}

_warmup_ollama_models() {
  local base="${OLLAMA_BASE_URL%/}"
  local chat_model="${QUIMERA_OLLAMA_CHAT_MODEL}"
  local embed_model="${QUIMERA_OLLAMA_EMBED_MODEL}"

  if ! curl -fsS --max-time 2 "${base}/api/version" >/dev/null 2>&1; then
    _warn "Ollama unavailable; skipping warmup"
    return 0
  fi

  if ! curl -fsS --max-time 30 -H 'Content-Type: application/json' \
    -d "{\"model\":\"${chat_model}\",\"prompt\":\"\",\"keep_alive\":-1,\"stream\":false}" \
    "${base}/api/generate" >/dev/null 2>&1; then
    _warn "Ollama chat model unavailable; rode: ollama pull ${chat_model}"
  fi

  if ! curl -fsS --max-time 30 -H 'Content-Type: application/json' \
    -d "{\"model\":\"${embed_model}\",\"input\":\"warmup\",\"keep_alive\":-1}" \
    "${base}/api/embed" >/dev/null 2>&1; then
    if ! curl -fsS --max-time 30 -H 'Content-Type: application/json' \
      -d "{\"model\":\"${embed_model}\",\"prompt\":\"\",\"keep_alive\":-1,\"stream\":false}" \
      "${base}/api/generate" >/dev/null 2>&1; then
      _warn "Ollama embed model unavailable; rode: ollama pull ${embed_model}"
    fi
  fi
}

_release_ollama_models() {
  local base="${OLLAMA_BASE_URL%/}"

  if ! curl -fsS --max-time 2 "${base}/api/version" >/dev/null 2>&1; then
    return 0
  fi

  curl -fsS --max-time 10 -H 'Content-Type: application/json' \
    -d "{\"model\":\"${QUIMERA_OLLAMA_CHAT_MODEL}\",\"prompt\":\"\",\"keep_alive\":0,\"stream\":false}" \
    "${base}/api/generate" >/dev/null 2>&1 || _warn "Could not unload ${QUIMERA_OLLAMA_CHAT_MODEL}"
  curl -fsS --max-time 10 -H 'Content-Type: application/json' \
    -d "{\"model\":\"${QUIMERA_OLLAMA_EMBED_MODEL}\",\"prompt\":\"\",\"keep_alive\":0,\"stream\":false}" \
    "${base}/api/generate" >/dev/null 2>&1 || _warn "Could not unload ${QUIMERA_OLLAMA_EMBED_MODEL}"
}

_run_shutdown_hooks() {
  local hook
  for hook in \
    "${REPO_ROOT}/infra/ollama/shutdown_hook.py" \
    "${REPO_ROOT}/scripts/hooks/qdrant_hot_cache_snapshot.sh" \
    "${REPO_ROOT}/backend/working_memory/shutdown_hook.py"; do
    if [[ -x "${hook}" ]]; then
      "${hook}" || _warn "Shutdown hook failed: ${hook}"
    elif [[ -f "${hook}" && "${hook}" == *.py ]]; then
      uv run python "${hook}" || _warn "Shutdown hook failed: ${hook}"
    fi
  done
}

_service_status_row() {
  local service="$1"
  local container_id
  local status="missing"
  local image="-"
  local health="-"

  container_id="$(_service_container_id "${service}")"
  if [[ -n "${container_id}" ]]; then
    status="$(docker inspect -f '{{.State.Status}}' "${container_id}" 2>/dev/null || printf 'unknown')"
    image="$(docker inspect -f '{{.Config.Image}}' "${container_id}" 2>/dev/null || printf 'unknown')"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}" 2>/dev/null || printf 'unknown')"
  fi
  printf '%s | %s | %s | %s | %s\n' "${service}" "${status}" "${image}" "docker" "${health}"
}

_status_table() {
  local service
  local postgres_service
  local qdrant_url="${QDRANT_API_BASE%/}"
  local litellm_url="${LITELLM_BASE_URL%/}"
  local ollama_url="${OLLAMA_BASE_URL%/}"

  printf 'SERVIÇO | STATUS | VERSÃO/IMAGEM | PORTA/URL | HEALTH\n'
  printf '%s\n' '--- | --- | --- | --- | ---'

  while read -r service; do
    [[ -n "${service}" ]] || continue
    _service_status_row "${service}"
  done < <(_compose config --services)

  postgres_service="$(_detect_postgres_service || true)"
  if [[ -n "${postgres_service}" ]]; then
    local pg_container
    local pg_version="-"
    pg_container="$(_service_container_id "${postgres_service}")"
    if [[ -n "${pg_container}" ]]; then
      pg_version="$(docker exec "${pg_container}" psql -U quimera -d quimera -Atc 'SHOW server_version' 2>/dev/null || printf '-')"
      printf 'postgres-version | running | %s | 5432 | checked\n' "${pg_version}"
    fi
  fi

  if [[ "$(_detect_ollama_runtime)" == "host" ]]; then
    if curl -fsS --max-time 2 "${ollama_url}/api/version" >/dev/null 2>&1; then
      local ollama_version
      ollama_version="$(curl -fsS --max-time 2 "${ollama_url}/api/version" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version","unknown"))' 2>/dev/null || printf 'unknown')"
      printf 'ollama-host | host-ok | %s | %s | /api/version\n' "${ollama_version}" "${ollama_url}"
    else
      printf 'ollama-host | host-fail | - | %s | /api/version\n' "${ollama_url}"
    fi
  fi

  if curl -fsS --max-time 2 "${qdrant_url}/readyz" >/dev/null 2>&1; then
    local qdrant_version
    qdrant_version="$(curl -fsS --max-time 2 "${qdrant_url}/" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version","unknown"))' 2>/dev/null || printf 'unknown')"
    printf 'qdrant-http | host-ok | %s | %s | /readyz\n' "${qdrant_version}" "${qdrant_url}"
  elif curl -fsS --max-time 2 "${qdrant_url}/healthz" >/dev/null 2>&1; then
    printf 'qdrant-http | host-ok | unknown | %s | /healthz\n' "${qdrant_url}"
  else
    printf 'qdrant-http | host-fail | - | %s | /readyz\n' "${qdrant_url}"
  fi

  if [[ "$(_detect_litellm_runtime)" == "host" ]]; then
    if curl -fsS --max-time 2 "${litellm_url}/health/readiness" >/dev/null 2>&1; then
      printf 'litellm-host | host-ok | readiness | %s | /health/readiness\n' "${litellm_url}"
    elif curl -fsS --max-time 2 "${litellm_url}/health" >/dev/null 2>&1; then
      _warn "LiteLLM /health/readiness unavailable; fallback /health used"
      printf 'litellm-host | host-ok | readiness-fallback | %s | /health\n' "${litellm_url}"
    else
      printf 'litellm-host | host-fail | - | %s | /health/readiness\n' "${litellm_url}"
    fi
  fi
}

_status_table_without_docker() {
  local qdrant_url="${QDRANT_API_BASE%/}"
  local litellm_url="${LITELLM_BASE_URL%/}"
  local ollama_url="${OLLAMA_BASE_URL%/}"

  printf 'SERVIÇO | STATUS | VERSÃO/IMAGEM | PORTA/URL | HEALTH\n'
  printf '%s\n' '--- | --- | --- | --- | ---'
  printf 'docker | unavailable | - | local daemon | skipped\n'

  if curl -fsS --max-time 2 "${ollama_url}/api/version" >/dev/null 2>&1; then
    printf 'ollama-host | host-ok | unknown | %s | /api/version\n' "${ollama_url}"
  else
    printf 'ollama-host | host-fail | - | %s | /api/version\n' "${ollama_url}"
  fi

  if curl -fsS --max-time 2 "${qdrant_url}/readyz" >/dev/null 2>&1; then
    printf 'qdrant-http | host-ok | unknown | %s | /readyz\n' "${qdrant_url}"
  elif curl -fsS --max-time 2 "${qdrant_url}/healthz" >/dev/null 2>&1; then
    printf 'qdrant-http | host-ok | unknown | %s | /healthz\n' "${qdrant_url}"
  else
    printf 'qdrant-http | unknown | - | %s | docker-unavailable\n' "${qdrant_url}"
  fi

  if curl -fsS --max-time 2 "${litellm_url}/health/readiness" >/dev/null 2>&1; then
    printf 'litellm-host | host-ok | readiness | %s | /health/readiness\n' "${litellm_url}"
  else
    printf 'litellm-host | host-fail | - | %s | /health/readiness\n' "${litellm_url}"
  fi
}

_start() {
  _load_env
  mkdir -p "${RUNTIME_DIR}"
  _check_docker
  _rebuild_postgres_if_needed

  if _compose up -d --wait --wait-timeout "${QUIMERA_WAIT_TIMEOUT}"; then
    :
  else
    _warn "docker compose --wait unavailable or failed; using polling fallback"
    _compose up -d
    while read -r service; do
      _wait_service_healthy "${service}" || _warn "Service not healthy: ${service}"
    done < <(_compose config --services)
  fi

  _warmup_ollama_models
  _wait_http_200 "${QDRANT_API_BASE%/}/readyz" "Qdrant" 5 || _wait_http_200 "${QDRANT_API_BASE%/}/healthz" "Qdrant" 5 || true
  _wait_http_200 "${LITELLM_BASE_URL%/}/health/readiness" "LiteLLM" 5 || _warn "LiteLLM readiness unavailable"
  _status_table
}

_stop() {
  _load_env
  _release_ollama_models
  _run_shutdown_hooks
  _check_docker
  _compose stop
  _status_table
}

_status() {
  _load_env
  if ! _docker_available; then
    _warn "Docker unavailable; showing partial host-only status"
    _status_table_without_docker
    return 0
  fi
  _status_table
}

main() {
  if [[ $# -ne 1 ]]; then
    _usage
    exit 2
  fi

  case "$1" in
    --start) _start ;;
    --stop) _stop ;;
    --status) _status ;;
    *) _usage; exit 2 ;;
  esac
}

main "$@"
