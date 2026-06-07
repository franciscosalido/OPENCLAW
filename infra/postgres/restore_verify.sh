#!/usr/bin/env bash
# Restore a custom-format backup into an isolated temporary database.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: infra/postgres/restore_verify.sh <dump-file>" >&2
  exit 3
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DUMP_FILE="$1"
if [[ ! -f "${DUMP_FILE}" ]]; then
  echo "dump file not found" >&2
  exit 3
fi

RESTORE_DB="quimera_restore_verify_$(date -u +%Y%m%dT%H%M%S)_$$"
case "${RESTORE_DB}" in
  quimera_restore_verify_*) ;;
  *) echo "unsafe restore database name" >&2; exit 3 ;;
esac

DATABASE="${QUIMERA_POSTGRES_DATABASE:-${POSTGRES_DB:-quimera}}"
admin_args=()
restore_args=()
base_dsn=""
if [[ -n "${QUIMERA_POSTGRES_ADMIN_DSN:-}" ]]; then
  admin_args+=(--dbname "${QUIMERA_POSTGRES_ADMIN_DSN}")
  base_dsn="${QUIMERA_POSTGRES_ADMIN_DSN}"
elif [[ -n "${QUIMERA_POSTGRES_DSN:-}" ]]; then
  admin_args+=(--dbname "${QUIMERA_POSTGRES_DSN}")
  base_dsn="${QUIMERA_POSTGRES_DSN}"
elif [[ -n "${TEST_POSTGRES_DSN:-}" ]]; then
  admin_args+=(--dbname "${TEST_POSTGRES_DSN}")
  base_dsn="${TEST_POSTGRES_DSN}"
else
  admin_args+=(
    --host "${POSTGRES_HOST:-127.0.0.1}"
    --port "${POSTGRES_PORT:-5432}"
    --username "${POSTGRES_USER:-quimera}"
    --dbname "${DATABASE}"
  )
  restore_args+=(
    --host "${POSTGRES_HOST:-127.0.0.1}"
    --port "${POSTGRES_PORT:-5432}"
    --username "${POSTGRES_USER:-quimera}"
    --dbname "${RESTORE_DB}"
  )
fi
if [[ -n "${base_dsn}" ]]; then
  restore_dsn="$(uv run python - "${base_dsn}" "${RESTORE_DB}" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

dsn = sys.argv[1]
db = sys.argv[2]
parts = urlsplit(dsn)
path = "/" + db
print(urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)))
PY
)"
  restore_args+=(--dbname "${restore_dsn}")
fi

cleanup() {
  if [[ "${QUIMERA_BACKUP_KEEP_RESTORE_DB:-0}" == "1" ]]; then
    echo "restore_db_kept=${RESTORE_DB}" >&2
    return
  fi
  case "${RESTORE_DB}" in
    quimera_restore_verify_*)
      # DROP DATABASE is guarded by the quimera_restore_verify_ prefix above.
      psql "${admin_args[@]}" -v restore_db="${RESTORE_DB}" -c 'DROP DATABASE IF EXISTS :"restore_db" WITH (FORCE)' >/dev/null 2>&1 || true
      ;;
  esac
}
trap cleanup EXIT

psql "${admin_args[@]}" -v restore_db="${RESTORE_DB}" -c 'CREATE DATABASE :"restore_db"' >/dev/null
pg_restore --exit-on-error "${restore_args[@]}" "${DUMP_FILE}"
psql "${restore_args[@]}" -Atqc "SELECT 1" >/dev/null

for table in sessions turns agent_states entity_mentions; do
  psql "${restore_args[@]}" -v table="${table}" -Atqc \
    "SELECT to_regclass('public.${table}') IS NOT NULL" >/dev/null
done

MANIFEST_FILE="${DUMP_FILE%.dump}.manifest.json"
if [[ -f "${MANIFEST_FILE}" ]]; then
  uv run python -m infra.postgres.backup_manifest mark-restore-verified --manifest "${MANIFEST_FILE}" >/dev/null
fi

printf 'restore_verified=true\n'
