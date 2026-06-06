#!/usr/bin/env bash
# PR-09 operational smoke.
# Uses docker compose up --wait when available, then poll_health_fallback.
# Summary artifact: evaluation/results/rag_01b_pr09_smoke_summary.json
# Exit codes: 0: ok, 1: fail, 2: degraded, 3: configuration error, 4: backup/restore verification failed, 5: latency regression
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/compose.quimera.local.yml"
MODE="quick"
JSON=0
LEAVE_RUNNING=0
NO_BUILD=0
TIMEOUT=90
ALLOW_DEGRADED=0
ALLOW_LATENCY_REGRESSION=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) MODE="quick" ;;
    --full) MODE="full" ;;
    --diagnostic) MODE="diagnostic" ;;
    --json) JSON=1 ;;
    --leave-running) LEAVE_RUNNING=1 ;;
    --no-build) NO_BUILD=1 ;;
    --timeout) TIMEOUT="$2"; shift ;;
    --allow-degraded) ALLOW_DEGRADED=1 ;;
    --allow-latency-regression) ALLOW_LATENCY_REGRESSION=1 ;;
    --help|-h)
      sed -n '1,40p' "$0"
      exit 0
      ;;
    *) echo "unknown flag: $1" >&2; exit 3 ;;
  esac
  shift
done

compose_up() {
  if ! command -v docker >/dev/null 2>&1; then
    return 2
  fi
  local args=(compose -f "${COMPOSE_FILE}" up --detach --wait --wait-timeout "${TIMEOUT}")
  if [[ "${NO_BUILD}" -eq 0 ]]; then
    args+=(--build)
  fi
  if docker "${args[@]}" >/dev/null 2>&1; then
    return 0
  fi
  poll_health_fallback
}

poll_health_fallback() {
  local deadline=$((SECONDS + TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 2 http://127.0.0.1:6333/healthz >/dev/null 2>&1 || curl -fsS --max-time 2 http://127.0.0.1:6333/readyz >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 2
}

compose_up || true

summary_args=(--mode "${MODE}")
if [[ "${JSON}" -eq 1 ]]; then
  summary_args+=(--json)
fi
if [[ "${ALLOW_LATENCY_REGRESSION}" -eq 1 ]]; then
  summary_args+=(--allow-latency-regression)
fi

set +e
output="$(uv run python -m integration.smoke_summary "${summary_args[@]}")"
rc=$?
set -e

if [[ "${JSON}" -eq 1 ]]; then
  printf '%s\n' "${output}"
else
  printf '%s\n' "${output}"
fi

if [[ "${rc}" -eq 2 && "${ALLOW_DEGRADED}" -eq 1 ]]; then
  exit 0
fi
if [[ "${MODE}" != "quick" && "${QUIMERA_SMOKE_VERIFY_RESTORE:-0}" == "1" ]]; then
  if ! "${REPO_ROOT}/infra/postgres/backup.sh" >/tmp/quimera_pr09_backup.out 2>/tmp/quimera_pr09_backup.err; then
    exit 4
  fi
fi
if [[ "${LEAVE_RUNNING}" -eq 0 ]]; then
  :
fi
exit "${rc}"
