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

mkdir -p "${BACKUP_DIR}"

pg_args=()
if [[ -n "${QUIMERA_POSTGRES_DSN:-}" ]]; then
  pg_args+=(--dbname "${QUIMERA_POSTGRES_DSN}")
elif [[ -n "${TEST_POSTGRES_DSN:-}" ]]; then
  pg_args+=(--dbname "${TEST_POSTGRES_DSN}")
else
  pg_args+=(
    --host "${POSTGRES_HOST:-127.0.0.1}"
    --port "${POSTGRES_PORT:-5432}"
    --username "${POSTGRES_USER:-quimera}"
    --dbname "${DATABASE}"
  )
fi

warnings=()
postgres_version="$(psql "${pg_args[@]}" -Atqc "SHOW server_version" 2>/dev/null || true)"
if [[ -z "${postgres_version}" ]]; then
  postgres_version="unknown"
  warnings+=(--warning "postgres version unavailable")
fi
pg_dump_version="$(pg_dump --version | awk '{print $NF}')"

pg_dump -Fc "${pg_args[@]}" --file "${DUMP_FILE}"
chmod 600 "${DUMP_FILE}" 2>/dev/null || true

uv run python -m infra.postgres.backup_manifest create \
  --dump-file "${DUMP_FILE}" \
  --database "${DATABASE}" \
  --postgres-version "${postgres_version}" \
  --pg-dump-version "${pg_dump_version}" \
  --retention-days "${RETENTION_DAYS}" \
  "${warnings[@]}" >/dev/null

uv run python -m infra.postgres.backup_manifest prune \
  --directory "${BACKUP_DIR}" \
  --retention-days "${RETENTION_DAYS}" >/dev/null

printf 'backup_created=%s\n' "${DUMP_FILE}"
