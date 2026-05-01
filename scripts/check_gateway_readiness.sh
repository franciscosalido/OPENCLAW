#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="static"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

ok() {
  printf 'OK: %s\n' "$1"
}

usage() {
  cat <<'EOF'
Usage: scripts/check_gateway_readiness.sh [--live]

Default mode is static and does not require network, live services, secrets, or
Qdrant access. --live performs explicit local service checks.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ "${1:-}" = "--live" ]; then
  MODE="live"
elif [ "${1:-}" != "" ]; then
  fail "Unknown argument '${1}'. Use --live or --help."
fi

require_file() {
  [ -f "${ROOT_DIR}/$1" ] || fail "Required file missing: $1"
  ok "found $1"
}

require_executable() {
  [ -x "${ROOT_DIR}/$1" ] || fail "Required executable missing: $1"
  ok "executable $1"
}

is_local_url() {
  case "$1" in
    http://127.0.0.1:*|http://localhost:*) return 0 ;;
    *) return 1 ;;
  esac
}

require_local_url() {
  local name="$1"
  local value="$2"
  if ! is_local_url "${value}"; then
    fail "${name} must be local-only. Got '${value}'."
  fi
  ok "${name} is local-only"
}

active_config() {
  sed '/^[[:space:]]*#/d' "${ROOT_DIR}/$1"
}

require_alias() {
  local file="$1"
  local alias="$2"
  if ! grep -Eq "model_name:[[:space:]]*${alias}([[:space:]]*)$" "${ROOT_DIR}/${file}"; then
    fail "Alias '${alias}' missing from ${file}"
  fi
  ok "${file} defines ${alias}"
}

reject_remote_markers() {
  local file="$1"
  local active
  active="$(active_config "${file}")"
  if printf '%s\n' "${active}" | grep -Eiq \
      'OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY|XAI_API_KEY|AZURE_API_KEY'; then
    fail "Remote provider API key marker found in active config ${file}"
  fi
  if printf '%s\n' "${active}" | grep -Eiq \
      'model:[[:space:]]*(openai|anthropic|gemini|google|openrouter|xai|azure)/'; then
    fail "Remote provider model found in active config ${file}"
  fi
  ok "${file} has no active remote provider markers"
}

require_grep() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  grep -Eq "${pattern}" "${ROOT_DIR}/${file}" || fail "${label} missing in ${file}"
  ok "${label}"
}

check_static() {
  require_file "config/rag_config.yaml"
  require_file "config/litellm_config.yaml"
  require_file "infra/litellm/litellm_config.yaml"
  require_file "infra/litellm/requirements.txt"
  require_file "docs/GATEWAY_FINAL_RUNBOOK.md"
  require_file "docs/ADR/0019-gateway-0-sprint-boundary.md"
  require_executable "infra/litellm/healthcheck.sh"
  require_executable "scripts/test_opencraw_litellm_runtime.sh"
  require_executable "scripts/test_local_embed_litellm.sh"
  require_executable "scripts/test_rag_e2e_gateway.sh"
  require_executable "scripts/test_gw08_embedding_migration.sh"

  for config in "config/litellm_config.yaml" "infra/litellm/litellm_config.yaml"; do
    for alias in local_chat local_think local_rag local_json quimera_embed local_embed; do
      require_alias "${config}" "${alias}"
    done
    reject_remote_markers "${config}"
  done

  require_grep "config/rag_config.yaml" 'tracing:[[:space:]]*$' "rag.tracing section"
  require_grep "config/rag_config.yaml" 'observability:[[:space:]]*$' "rag.observability section"
  require_grep "config/rag_config.yaml" 'active_backend:[[:space:]]*"gateway_litellm"' "gateway_litellm active backend"
  require_grep "config/rag_config.yaml" 'embedding_alias:[[:space:]]*"quimera_embed"' "quimera_embed embedding alias"
  require_grep "config/rag_config.yaml" 'embedding_dimensions:[[:space:]]*768' "768 embedding dimensions"
  require_grep "config/rag_config.yaml" 'reindex_required_on_model_change:[[:space:]]*true' "reindex-required metadata"

  require_grep "infra/litellm/requirements.txt" '!=1\.82\.7' "LiteLLM 1.82.7 exclusion"
  require_grep "infra/litellm/requirements.txt" '!=1\.82\.8' "LiteLLM 1.82.8 exclusion"

  require_grep "tests/smoke/test_gateway_runtime_smoke.py" 'RUN_LITELLM_SMOKE' "runtime smoke guard"
  require_grep "tests/smoke/test_gateway_embed_smoke.py" 'RUN_LITELLM_EMBED_SMOKE' "embedding smoke guard"
  require_grep "tests/smoke/test_rag_e2e_gateway_smoke.py" 'RUN_RAG_E2E_SMOKE' "RAG E2E smoke guard"
  require_grep "tests/smoke/test_rag_gateway_embedding_migration_smoke.py" 'RUN_GW08_EMBEDDING_MIGRATION_SMOKE' "GW08 migration smoke guard"
  require_grep "tests/smoke/test_rag_gateway_embedding_migration_smoke.py" 'RUN_GW08_EMBEDDING_PARITY_SMOKE' "GW08 parity smoke guard"

  require_local_url "QUIMERA_LLM_BASE_URL" "${QUIMERA_LLM_BASE_URL:-http://127.0.0.1:4000/v1}"
  require_local_url "OLLAMA_API_BASE" "${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
  require_local_url "QDRANT_URL" "${QDRANT_URL:-http://127.0.0.1:6333}"

  ok "Gateway-0 static readiness checks passed"
}

json_contains_alias() {
  local json_file="$1"
  local alias="$2"
  grep -q "\"${alias}\"" "${json_file}" || fail "LiteLLM /models did not expose ${alias}"
  ok "LiteLLM exposes ${alias}"
}

check_live() {
  command -v curl >/dev/null 2>&1 || fail "curl is required for --live" 127
  command -v python3 >/dev/null 2>&1 || fail "python3 is required for --live" 127
  [ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY is required for --live"
  [ -n "${QUIMERA_LLM_API_KEY:-}" ] || fail "QUIMERA_LLM_API_KEY is required for --live"

  local llm_base="${QUIMERA_LLM_BASE_URL:-http://127.0.0.1:4000/v1}"
  local ollama_base="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
  local qdrant_url="${QDRANT_URL:-http://127.0.0.1:6333}"

  require_local_url "QUIMERA_LLM_BASE_URL" "${llm_base}"
  require_local_url "OLLAMA_API_BASE" "${ollama_base}"
  require_local_url "QDRANT_URL" "${qdrant_url}"

  curl -fsS --max-time 5 "${qdrant_url%/}/healthz" >/dev/null || fail "Qdrant is not reachable at ${qdrant_url}"
  ok "Qdrant healthz reachable"
  curl -fsS --max-time 5 "${ollama_base%/}/api/tags" >/dev/null || fail "Ollama is not reachable at ${ollama_base}"
  ok "Ollama tags reachable"

  local models_json
  models_json="$(mktemp)"
  curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${QUIMERA_LLM_API_KEY}" \
    "${llm_base%/}/models" > "${models_json}" || fail "LiteLLM /v1/models is not reachable"
  for alias in local_chat local_think local_rag local_json quimera_embed local_embed; do
    json_contains_alias "${models_json}" "${alias}"
  done
  rm -f "${models_json}"

  local embed_json
  embed_json="$(mktemp)"
  curl -fsS --max-time 30 \
    -H "Authorization: Bearer ${QUIMERA_LLM_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"model":"quimera_embed","input":"texto sintetico curto para readiness"}' \
    "${llm_base%/}/embeddings" > "${embed_json}" || fail "quimera_embed embedding call failed"
  local dims
  dims="$(python3 - "${embed_json}" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as fh:
    body = json.load(fh)
print(len(body["data"][0]["embedding"]))
PY
)"
  rm -f "${embed_json}"
  [ "${dims}" = "768" ] || fail "quimera_embed returned ${dims} dimensions, expected 768"
  ok "quimera_embed returns 768 dimensions"

  (cd "${ROOT_DIR}/infra/litellm" && ./healthcheck.sh)
  ok "Gateway-0 live readiness checks passed"
}

check_static
if [ "${MODE}" = "live" ]; then
  check_live
fi
