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

URL="http://${LITELLM_HOST}:${LITELLM_PORT}/v1/chat/completions"
PAYLOAD='{"model":"local_chat","messages":[{"role":"user","content":"Responda em uma frase curta: o que e um teste local?"}],"temperature":0,"max_tokens":64}'

if ! RESPONSE="$(curl -fsS --max-time 60 -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" -H "Content-Type: application/json" -d "${PAYLOAD}" "${URL}")"; then
  fail "LiteLLM chat completion failed at ${URL}. Check LiteLLM and Ollama/Qwen."
fi

python3 -c '
import json
import sys

raw = sys.stdin.read()
try:
    body = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"ERROR: chat completion did not return valid JSON: {exc}") from exc

choices = body.get("choices")
if not isinstance(choices, list) or not choices:
    raise SystemExit("ERROR: chat completion response has no choices.")

message = choices[0].get("message") if isinstance(choices[0], dict) else None
content = message.get("content") if isinstance(message, dict) else None
if not isinstance(content, str) or not content.strip():
    raise SystemExit("ERROR: chat completion returned empty content.")

compact = " ".join(content.split())
print(f"OK: local_chat responded: {compact[:180]}")
' <<< "${RESPONSE}"
