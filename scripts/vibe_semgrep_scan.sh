#!/usr/bin/env bash
# Run Semgrep outside the project virtualenv so Semgrep dependencies cannot
# constrain QUIMERA runtime dependencies such as OpenTelemetry.
set -euo pipefail

REPO_ROOT="${QUIMERA_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"

if [[ "$#" -eq 0 ]]; then
    set -- scan --config auto .
fi

if command -v docker >/dev/null 2>&1 && [[ "${QUIMERA_SEMGREP_USE_DOCKER:-1}" != "0" ]]; then
    docker run --rm \
        -v "${REPO_ROOT}:/src:ro" \
        -w /src \
        semgrep/semgrep:latest \
        semgrep "$@"
elif command -v uvx >/dev/null 2>&1; then
    uvx semgrep "$@"
else
    echo "[vibe-semgrep] docker or uvx is required to run isolated Semgrep" >&2
    exit 127
fi
