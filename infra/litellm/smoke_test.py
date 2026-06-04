from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SmokeResult:
    readiness: bool
    liveliness: bool
    models: bool
    chat: bool | None = None

    @property
    def ok(self) -> bool:
        return self.readiness and self.liveliness and self.models and self.chat is not False


def run_smoke(base_url: str, api_key: str | None = None, *, test_chat: bool = False) -> SmokeResult:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    with httpx.Client(timeout=10.0) as client:
        readiness = client.get(f"{base}/health/readiness").status_code < 400
        liveliness = client.get(f"{base}/health/liveliness").status_code < 400
        models = client.get(f"{base}/v1/models", headers=headers).status_code < 400
        chat_ok: bool | None = None
        if test_chat:
            payload = {
                "model": "local_chat",
                "messages": [{"role": "user", "content": "respond with ok"}],
                "max_tokens": 8,
            }
            chat_ok = client.post(
                f"{base}/v1/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
                timeout=130.0,
            ).status_code < 400
    return SmokeResult(readiness=readiness, liveliness=liveliness, models=models, chat=chat_ok)


def main() -> int:
    result = run_smoke(
        os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
        os.environ.get("QUIMERA_LLM_API_KEY") or os.environ.get("LITELLM_MASTER_KEY"),
        test_chat=os.environ.get("QUIMERA_LITELLM_TEST_CHAT") == "1",
    )
    sys.stdout.write(f"readiness={result.readiness}\n")
    sys.stdout.write(f"liveliness={result.liveliness}\n")
    sys.stdout.write(f"models={result.models}\n")
    if result.chat is not None:
        sys.stdout.write(f"chat={result.chat}\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
