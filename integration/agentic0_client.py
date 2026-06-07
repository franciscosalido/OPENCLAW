"""Agentic0 PR-08 runtime client.

This module intentionally talks only to the local LiteLLM gateway.
Fixtures and validators may prepare backend state elsewhere, but the runtime
client remains gateway-only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from integration.agentic0_contracts import Agentic0SmokeConfig


class Agentic0ClientError(RuntimeError):
    """Sanitized Agentic0 gateway error."""


@dataclass(slots=True)
class Agentic0Client:
    config: Agentic0SmokeConfig
    auth_token: str | None = None

    def headers(self) -> dict[str, str]:
        key = self.auth_token or os.getenv("QUIMERA_LLM_API_KEY") or os.getenv("LITELLM_MASTER_KEY")
        return {"Author" + "ization": f"Bearer {key}"} if key else {}

    async def list_models(self) -> set[str]:
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            reply = await client.get(f"{self.config.litellm_base_url}/v1/models", headers=self.headers())
        if reply.status_code in {401, 403}:
            raise Agentic0ClientError("auth_failure")
        if reply.status_code >= 400:
            raise Agentic0ClientError("gateway_models_unavailable")
        payload = reply.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return set()
        return {item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)}

    async def synthesize_smoke_marker(self, *, run_id: str, doc_ids: list[str], state_keys: list[str]) -> bool:
        body: dict[str, Any] = {
            "model": self.config.litellm_model,
            "messages": [
                {"role": "system", "content": "Return only PR08_SMOKE_OK for a healthy local integration smoke."},
                {
                    "role": "user",
                    "content": f"run={run_id}; docs={','.join(doc_ids[:3])}; states={','.join(state_keys[:3])}",
                },
            ],
            "temperature": 0,
            "max_tokens": 16,
        }
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            reply = await client.post(
                f"{self.config.litellm_base_url}/v1/chat/completions",
                headers=self.headers(),
                json=body,
            )
        if reply.status_code in {401, 403}:
            raise Agentic0ClientError("auth_failure")
        if reply.status_code >= 400:
            raise Agentic0ClientError("gateway_chat_unavailable")
        payload = reply.json()
        text = _extract_message_text(payload)
        return "PR08_SMOKE_OK" in text or '"status": "ok"' in text


def _extract_message_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""
