#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

[ -n "${QUIMERA_LLM_API_KEY:-}" ] || fail "QUIMERA_LLM_API_KEY is required and should match LITELLM_MASTER_KEY."

QUIMERA_LLM_BASE_URL="${QUIMERA_LLM_BASE_URL:-http://127.0.0.1:4000/v1}"
QUIMERA_LLM_MODEL="${QUIMERA_LLM_MODEL:-local_chat}"
QUIMERA_LLM_REASONING_MODEL="${QUIMERA_LLM_REASONING_MODEL:-local_think}"
QUIMERA_LLM_RAG_MODEL="${QUIMERA_LLM_RAG_MODEL:-local_rag}"
QUIMERA_LLM_JSON_MODEL="${QUIMERA_LLM_JSON_MODEL:-local_json}"

case "${QUIMERA_LLM_BASE_URL}" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) fail "QUIMERA_LLM_BASE_URL must point to the local LiteLLM gateway. Got '${QUIMERA_LLM_BASE_URL}'." ;;
esac

command -v curl >/dev/null 2>&1 || fail "curl is required." 127

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || fail "python is required." 127

MODELS_BODY="$(mktemp)"
trap 'rm -f "${MODELS_BODY}"' EXIT
HTTP_STATUS="$(
  curl -sS --max-time 10 \
    -o "${MODELS_BODY}" \
    -w "%{http_code}" \
    -H "Authorization: Bearer ${QUIMERA_LLM_API_KEY}" \
    "${QUIMERA_LLM_BASE_URL%/}/models" || true
)"

case "${HTTP_STATUS}" in
  200) ;;
  401|403)
    fail "LiteLLM authentication failed. QUIMERA_LLM_API_KEY should match LITELLM_MASTER_KEY."
    ;;
  000)
    fail "LiteLLM /v1/models is not reachable. Start infra/litellm/start_litellm.sh."
    ;;
  *)
    fail "LiteLLM /v1/models returned HTTP ${HTTP_STATUS}."
    ;;
esac

printf 'OK: LiteLLM /models reachable at %s\n' "${QUIMERA_LLM_BASE_URL%/}/models"

"${PYTHON_BIN}" - <<'PY'
import asyncio
import json
import os
import time
from urllib.parse import urlparse

import httpx

from backend.gateway.client import GatewayChatClient, GatewayRuntimeConfig

MAX_REPEAT = 5
OVERHEAD_SECONDS = 2.0


ALIASES = [
    (
        os.environ.get("QUIMERA_LLM_MODEL", "local_chat"),
        "Explique em uma frase o que e risco de concentracao.",
        None,
    ),
    (
        os.environ.get("QUIMERA_LLM_REASONING_MODEL", "local_think"),
        "Planeje em uma frase como revisar uma hipotese sintetica.",
        None,
    ),
    (
        os.environ.get("QUIMERA_LLM_RAG_MODEL", "local_rag"),
        "Classifique esta pergunta sintetica: carteira hipotetica com 50% em FIIs.",
        None,
    ),
    (
        os.environ.get("QUIMERA_LLM_JSON_MODEL", "local_json"),
        (
            "Responda somente JSON valido, sem markdown: "
            '{"classe":"alocacao_sintetica","fiis":50,"renda_fixa":30,"acoes":20}'
        ),
        {"type": "json_object"},
    ),
]


def smoke_repeat_count() -> int:
    raw = os.environ.get("RUN_LITELLM_SMOKE_REPEAT", "1")
    try:
        repeat = int(raw)
    except ValueError as exc:
        raise SystemExit(
            f"ERROR: RUN_LITELLM_SMOKE_REPEAT must be an integer from 1 to {MAX_REPEAT}"
        ) from exc
    if repeat < 1:
        raise SystemExit("ERROR: RUN_LITELLM_SMOKE_REPEAT must be greater than zero")
    return min(repeat, MAX_REPEAT)


def base_url_host(base_url: str) -> str:
    return urlparse(base_url).netloc or "unknown"


async def main() -> None:
    config = GatewayRuntimeConfig.from_env().validated()
    repeat_count = smoke_repeat_count()
    host = base_url_host(config.base_url)
    async with GatewayChatClient(config=config) as client:
        for alias, prompt, response_format in ALIASES:
            timeout_budget = config.resolve_timeout(alias)
            allowed_elapsed = timeout_budget + OVERHEAD_SECONDS
            for attempt in range(1, repeat_count + 1):
                start = time.perf_counter()
                try:
                    answer = await client.chat_completion(
                        [{"role": "user", "content": prompt}],
                        model=alias,
                        temperature=0.0,
                        max_tokens=96,
                        response_format=response_format,
                    )
                    if alias == os.environ.get("QUIMERA_LLM_JSON_MODEL", "local_json"):
                        json.loads(answer)
                except httpx.HTTPStatusError as exc:
                    raise SystemExit(
                        f"ERROR: alias {alias} failed with HTTP "
                        f"{exc.response.status_code} at {host}"
                    ) from exc
                except Exception as exc:
                    raise SystemExit(
                        f"ERROR: alias {alias} failed at {host}: {exc}"
                    ) from exc

                elapsed_s = time.perf_counter() - start
                if elapsed_s >= allowed_elapsed:
                    raise SystemExit(
                        f"ERROR: alias {alias} exceeded timeout budget at {host}: "
                        f"elapsed_s={elapsed_s:.2f} timeout_s={timeout_budget:.1f} "
                        f"allowed_s={allowed_elapsed:.1f}"
                    )

                # Print truncated response (synthetic output only; no real portfolio data)
                compact = " ".join(answer.split())[:120]
                print(
                    f"OK: alias={alias} attempt={attempt}/{repeat_count} "
                    f"elapsed_s={elapsed_s:.2f} timeout_s={timeout_budget:.1f}: "
                    f"{compact}"
                )


asyncio.run(main())
PY
