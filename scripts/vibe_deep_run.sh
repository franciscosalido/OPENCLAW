#!/usr/bin/env bash
# Build and run the official Vibe sandbox against the current checkout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="${QUIMERA_VIBE_IMAGE:-vibe-sandbox:py312}"
DOCKERFILE="${QUIMERA_VIBE_DOCKERFILE:-${REPO_ROOT}/Dockerfile.openclaw-sandbox}"
NETWORK="${QUIMERA_VIBE_DOCKER_NETWORK:-}"
BUILD_IMAGE="${QUIMERA_VIBE_BUILD_IMAGE:-1}"

detect_network() {
  if [[ -n "${NETWORK}" ]]; then
    docker network inspect "${NETWORK}" >/dev/null
    printf '%s\n' "${NETWORK}"
    return 0
  fi
  if docker network inspect quimera_network >/dev/null 2>&1; then
    printf 'quimera_network\n'
    return 0
  fi
  if docker network inspect quimera-local_default >/dev/null 2>&1; then
    printf 'quimera-local_default\n'
    return 0
  fi
  return 1
}

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  docker build --pull -f "${DOCKERFILE}" -t "${IMAGE}" "${REPO_ROOT}"
fi

network_name="$(detect_network || true)"
network_args=()
postgres_host="host.docker.internal"
qdrant_url="http://host.docker.internal:6333"
if [[ -n "${network_name}" ]]; then
  network_args=(--network "${network_name}")
  postgres_host="quimera-postgres-memory"
  qdrant_url="http://quimera-qdrant:6333"
fi

default_cmd='scripts/vibe_sandbox_bootstrap.sh /workspace && python -m pytest tests/unit tests/integration tests/e2e tests/smoke -q'
if [[ "$#" -gt 0 ]]; then
  default_cmd="$*"
fi

docker run --rm \
  "${network_args[@]}" \
  --add-host=host.docker.internal:host-gateway \
  -v "${REPO_ROOT}:/workspace" \
  -w /workspace \
  -e QUIMERA_E2E=true \
  -e RUN_AGENT0_E2E="${RUN_AGENT0_E2E:-1}" \
  -e RUN_LITELLM_SMOKE="${RUN_LITELLM_SMOKE:-1}" \
  -e RUN_LITELLM_EMBED_SMOKE="${RUN_LITELLM_EMBED_SMOKE:-1}" \
  -e RUN_RAG_E2E_SMOKE="${RUN_RAG_E2E_SMOKE:-1}" \
  -e RUN_HYBRID_SMOKE="${RUN_HYBRID_SMOKE:-1}" \
  -e QDRANT_API_BASE="${QDRANT_API_BASE:-${qdrant_url}}" \
  -e QDRANT_URL="${QDRANT_URL:-${qdrant_url}}" \
  -e TEST_QDRANT_URL="${TEST_QDRANT_URL:-${qdrant_url}}" \
  -e QUIMERA_QDRANT_URL="${QUIMERA_QDRANT_URL:-${qdrant_url}}" \
  -e POSTGRES_HOST="${POSTGRES_HOST:-${postgres_host}}" \
  -e POSTGRES_PORT="${POSTGRES_PORT:-5432}" \
  -e POSTGRES_USER="${POSTGRES_USER:-quimera}" \
  -e QUIMERA_POSTGRES_DATABASE="${QUIMERA_POSTGRES_DATABASE:-quimera}" \
  -e LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://host.docker.internal:4000}" \
  -e QUIMERA_LLM_BASE_URL="${QUIMERA_LLM_BASE_URL:-http://host.docker.internal:4000/v1}" \
  -e OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}" \
  -e OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://host.docker.internal:11434}" \
  -e QUIMERA_LLM_API_KEY \
  -e LITELLM_MASTER_KEY \
  "${IMAGE}" \
  bash -c '
    set -euo pipefail
    export PATH="${VIRTUAL_ENV}/bin:${PATH}"
    if [[ -z "${TEST_POSTGRES_DSN:-}" && -f /workspace/infra/postgres/secrets/postgres_password.txt ]]; then
      password="$(tr -d "\r\n" < /workspace/infra/postgres/secrets/postgres_password.txt)"
      export TEST_POSTGRES_DSN="postgresql://${POSTGRES_USER}:${password}@${POSTGRES_HOST}:${POSTGRES_PORT}/${QUIMERA_POSTGRES_DATABASE}"
      export QUIMERA_POSTGRES_DSN="${TEST_POSTGRES_DSN}"
    fi
    '"${default_cmd}"'
  '
