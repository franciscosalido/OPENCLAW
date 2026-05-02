#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_AGENT0_LOCAL_SMOKE:-}" != "1" ]]; then
  echo "SKIP: set RUN_AGENT0_LOCAL_SMOKE=1 to run Agent-0 local smoke."
  exit 0
fi

if [[ -z "${QUIMERA_LLM_API_KEY:-}" ]]; then
  echo "ERROR: QUIMERA_LLM_API_KEY is required for live Agent-0 local smoke."
  exit 1
fi

QUIMERA_LLM_BASE_URL="${QUIMERA_LLM_BASE_URL:-http://127.0.0.1:4000/v1}"
case "$QUIMERA_LLM_BASE_URL" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *)
    echo "ERROR: QUIMERA_LLM_BASE_URL must be local. Refusing to run."
    exit 1
    ;;
esac

echo "OK: Agent-0 dry-run"
uv run python scripts/run_local_agent.py \
  "Explique em uma frase o que e uma decisao local." \
  --dry-run \
  --output json >/dev/null

echo "OK: Agent-0 local_chat"
uv run python scripts/run_local_agent.py \
  "Explique em uma frase o que e uma decisao local." \
  --output json >/dev/null

echo "OK: Agent-0 local_json"
uv run python scripts/run_local_agent.py \
  "Responda somente JSON valido: {\"classe\":\"sintetica\"}" \
  --json \
  --output json >/dev/null

echo "OK: Agent-0 local runner smoke completed."
