#!/usr/bin/env bash
# Local PostgreSQL custom-format backup. Never prints the DSN.
# Manifest implementation: infra/postgres/backup_manifest.py
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${QUIMERA_POSTGRES_BACKUP_DIR:-${REPO_ROOT}/.runtime/backups/postgres}"
RETENTION_DAYS="${QUIMERA_POSTGRES_BACKUP_RETENTION_DAYS:-7}"
DATABASE="${QUIMERA_POSTGRES_DATABASE:-${POSTGRES_DB:-quimera}}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="${BACKUP_DIR}/quimera_pg18_${DATABASE}_${TIMESTAMP}.dump"
POSTGRES_CONTAINER="${QUIMERA_POSTGRES_CONTAINER:-quimera-postgres-memory}"

mkdir -p "${BACKUP_DIR}"

container_pg_tools_available() {
  command -v docker >/dev/null 2>&1 || return 1
  docker inspect -f '{{.State.Running}}' "${POSTGRES_CONTAINER}" 2>/dev/null | grep -qx true || return 1
  docker exec "${POSTGRES_CONTAINER}" sh -lc 'command -v pg_dump' >/dev/null 2>&1
}

run_psql() {
  if [[ "${PG_TOOL_MODE}" == "container" ]]; then
    docker exec -i "${POSTGRES_CONTAINER}" psql "$@"
  else
    psql "$@"
  fi
}

run_pg_dump_version() {
  if [[ "${PG_TOOL_MODE}" == "container" ]]; then
    docker exec -i "${POSTGRES_CONTAINER}" pg_dump --version
  else
    pg_dump --version
  fi
}

run_pg_dump_to_file() {
  if [[ "${PG_TOOL_MODE}" == "container" ]]; then
    docker exec -i "${POSTGRES_CONTAINER}" pg_dump -Fc "${pg_args[@]}" > "${DUMP_FILE}"
  else
    pg_dump -Fc "${pg_args[@]}" --file "${DUMP_FILE}"
  fi
}

PG_TOOL_MODE="host"
if container_pg_tools_available; then
  PG_TOOL_MODE="container"
fi

pg_args=()
if [[ -n "${QUIMERA_POSTGRES_DSN:-}" ]]; then
  pg_args+=(--dbname "${QUIMERA_POSTGRES_DSN}")
elif [[ -n "${TEST_POSTGRES_DSN:-}" ]]; then
  pg_args+=(--dbname "${TEST_POSTGRES_DSN}")
elif [[ "${PG_TOOL_MODE}" == "container" ]]; then
  pg_args+=(
    --username "${POSTGRES_USER:-quimera}"
    --dbname "${DATABASE}"
  )
else
  pg_args+=(
    --host "${POSTGRES_HOST:-127.0.0.1}"
    --port "${POSTGRES_PORT:-5432}"
    --username "${POSTGRES_USER:-quimera}"
    --dbname "${DATABASE}"
  )
fi

warnings=()
postgres_version="$(run_psql "${pg_args[@]}" -Atqc "SHOW server_version" 2>/dev/null || true)"
if [[ -z "${postgres_version}" ]]; then
  postgres_version="unknown"
  warnings+=(--warning "postgres version unavailable")
fi
pg_dump_version="$(run_pg_dump_version | awk '{print $NF}')"

run_pg_dump_to_file
chmod 600 "${DUMP_FILE}" 2>/dev/null || true

manifest_args=(
  --dump-file "${DUMP_FILE}" \
  --database "${DATABASE}" \
  --postgres-version "${postgres_version}" \
  --pg-dump-version "${pg_dump_version}" \
  --retention-days "${RETENTION_DAYS}"
)
if [[ "${#warnings[@]}" -gt 0 ]]; then
  manifest_args+=("${warnings[@]}")
fi

uv run python -m infra.postgres.backup_manifest create "${manifest_args[@]}" >/dev/null

uv run python -m infra.postgres.backup_manifest prune \
  --directory "${BACKUP_DIR}" \
  --retention-days "${RETENTION_DAYS}" >/dev/null

printf 'backup_created=%s\n' "${DUMP_FILE}"
