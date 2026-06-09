#!/usr/bin/env bash
# Move a disposable virtualenv to a reversible patio location.
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'Usage: %s /absolute/path/to/.venv\n' "$0" >&2
  exit 2
fi

source_path="$1"
patio_root="${QUIMERA_VENV_PATIO:-/Users/fas/projetos/_patio_venvs}"

case "${source_path}" in
  /*/.venv|*/.venv) ;;
  *)
    printf 'Refusing to move non-venv path: %s\n' "${source_path}" >&2
    exit 2
    ;;
esac

if [[ ! -d "${source_path}" ]]; then
  printf 'Nothing to quarantine; path is absent: %s\n' "${source_path}" >&2
  exit 0
fi

mkdir -p "${patio_root}"
parent_name="$(basename "$(dirname "${source_path}")")"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${patio_root}/${parent_name}.venv.${timestamp}"

mv "${source_path}" "${target}"
printf 'quarantined=%s\n' "${target}"
