#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

command -v curl >/dev/null 2>&1 || fail "curl is required." 127
command -v python3 >/dev/null 2>&1 || fail "python3 is required for response validation." 127

[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY is required."

LITELLM_HOST="${LITELLM_HOST:-127.0.0.1}"
LITELLM_PORT="${LITELLM_PORT:-4000}"
[ "${LITELLM_HOST}" = "127.0.0.1" ] || fail "Refusing non-local LiteLLM host '${LITELLM_HOST}'."

URL="http://${LITELLM_HOST}:${LITELLM_PORT}/v1/models"

if ! RESPONSE="$(curl -fsS --max-time 10 -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" "${URL}")"; then
  fail "LiteLLM /v1/models is not reachable at ${URL}. Is start_litellm.sh running?"
fi

python3 -c '
import json
import sys

expected = {"local_chat", "local_think", "local_rag", "local_json", "local_embed"}
raw = sys.stdin.read()
try:
    body = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"ERROR: /v1/models did not return valid JSON: {exc}") from exc

data = body.get("data")
if not isinstance(data, list):
    raise SystemExit("ERROR: /v1/models response is missing a data list.")

seen = {
    str(item.get("id") or item.get("model_name") or item.get("model") or "")
    for item in data
    if isinstance(item, dict)
}
missing = sorted(expected - seen)
if missing:
    raise SystemExit(f"ERROR: Missing LiteLLM aliases: {missing}. Seen: {sorted(seen)}")

print("OK: /v1/models exposes local gateway aliases.")
' <<< "${RESPONSE}"
