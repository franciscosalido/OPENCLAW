"""Semantic health checks for the gateway's local service dependencies.

Unlike a plain HTTP-200 check, these checks verify that the specific models
required by the gateway aliases are *actually available* in Ollama — not
just that the server process is running.

Typical call site (CLI entry point)::

    from backend.gateway.health import check_gateway_services

    check_gateway_services()          # require chat + embed
    check_gateway_services(require_embed=False)  # chat only
"""

from __future__ import annotations

import sys
from typing import Any

import httpx
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    DEFAULT_LLM_REASONING_MODEL,
    ENV_LLM_API_KEY,
    GatewayRuntimeConfig,
)

# ─── Constants ────────────────────────────────────────────────────────────────

OLLAMA_TAGS_URL: str = "http://localhost:11434/api/tags"
REQUIRED_GATEWAY_ALIASES: frozenset[str] = frozenset(
    {
        DEFAULT_LLM_MODEL,
        DEFAULT_LLM_REASONING_MODEL,
        DEFAULT_LLM_RAG_MODEL,
        DEFAULT_LLM_JSON_MODEL,
    }
)

#: Base name of the chat/reasoning model required by local_chat, local_think,
#: local_rag, and local_json aliases.
REQUIRED_CHAT_MODEL: str = "qwen3:14b"

#: Base name of the embedding model required by the local_embed alias.
REQUIRED_EMBED_MODEL: str = "nomic-embed-text"

PREFLIGHT_TIMEOUT_SECONDS: float = 3.0


# ─── Public API ───────────────────────────────────────────────────────────────


def check_gateway_services(
    *,
    require_chat: bool = True,
    require_embed: bool = True,
) -> None:
    """Verify that Ollama is reachable and the required models are loaded.

    This is a *semantic* check: it confirms not only that Ollama responds to
    HTTP but that the specific models required by the five gateway aliases are
    present in ``ollama list``. A server that is running but missing a model
    will fail here with an actionable pull command rather than deep inside the
    LiteLLM call path.

    Exits the process with status 1 on any failure, printing a human-readable
    message with a suggested corrective command.

    Args:
        require_chat: Verify that :data:`REQUIRED_CHAT_MODEL` is available.
        require_embed: Verify that :data:`REQUIRED_EMBED_MODEL` is available.
    """
    tags = _fetch_ollama_tags()

    models: list[dict[str, Any]] = []
    raw_models = tags.get("models")
    if isinstance(raw_models, list):
        models = [m for m in raw_models if isinstance(m, dict)]

    available: set[str] = {str(m.get("name", "")) for m in models}
    # Base names (without :tag suffix) for loose matching, e.g. "qwen3" matches
    # "qwen3:14b-instruct-q4_K_M".
    base_names: set[str] = {name.split(":")[0] for name in available if name}

    if require_chat:
        _assert_model_available(
            REQUIRED_CHAT_MODEL,
            available,
            base_names,
            pull_hint=f"ollama pull {REQUIRED_CHAT_MODEL}",
        )

    if require_embed:
        _assert_model_available(
            REQUIRED_EMBED_MODEL,
            available,
            base_names,
            pull_hint=f"ollama pull {REQUIRED_EMBED_MODEL}",
        )

    logger.debug(
        "Gateway service check passed (chat={}, embed={})",
        require_chat,
        require_embed,
    )


def check_litellm_gateway() -> None:
    """Verify that local LiteLLM is reachable and exposes runtime aliases.

    This check only validates the local gateway surface. It does not call
    remote providers, Qdrant, embeddings, or RAG retrieval.
    """
    try:
        config = GatewayRuntimeConfig.from_env().validated()
    except Exception as exc:
        print(f"ERROR: LiteLLM gateway configuration invalid: {exc}")
        sys.exit(1)

    models_url = f"{config.base_url.rstrip('/')}/models"
    try:
        response = httpx.get(
            models_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            print(
                "ERROR: LiteLLM authentication failed.\n"
                f"  Ensure {ENV_LLM_API_KEY} matches LITELLM_MASTER_KEY."
            )
        else:
            print(
                f"ERROR: LiteLLM returned HTTP {exc.response.status_code} at "
                f"{models_url}."
            )
        sys.exit(1)
    except httpx.RequestError:
        print(
            f"ERROR: LiteLLM is not reachable at {models_url}.\n"
            "  Start it with: infra/litellm/start_litellm.sh"
        )
        sys.exit(1)

    raw: object = response.json()
    if not isinstance(raw, dict):
        print("ERROR: LiteLLM /models response was not a JSON object.")
        sys.exit(1)
    data = raw.get("data")
    if not isinstance(data, list):
        print("ERROR: LiteLLM /models response is missing a data list.")
        sys.exit(1)
    seen = {
        str(item.get("id") or item.get("model_name") or item.get("model") or "")
        for item in data
        if isinstance(item, dict)
    }
    missing = sorted(REQUIRED_GATEWAY_ALIASES - seen)
    if missing:
        print(f"ERROR: LiteLLM is missing required aliases: {missing}")
        sys.exit(1)

    logger.debug(
        "LiteLLM gateway check passed | base_url_host={} aliases={}",
        config.base_url.replace("http://", "").replace("https://", ""),
        sorted(REQUIRED_GATEWAY_ALIASES),
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _fetch_ollama_tags() -> dict[str, Any]:
    """Fetch the Ollama model list. Exits with status 1 on any failure."""
    try:
        response = httpx.get(OLLAMA_TAGS_URL, timeout=PREFLIGHT_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.ConnectError:
        logger.error("Ollama is not reachable at {}", OLLAMA_TAGS_URL)
        print(
            "ERROR: Ollama is not running.\n"
            "  Start it with:  ollama serve\n"
            f"  Then verify:    curl -fsS {OLLAMA_TAGS_URL}"
        )
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama returned unexpected status {}",
            exc.response.status_code,
        )
        print(
            f"ERROR: Ollama returned HTTP {exc.response.status_code}.\n"
            "  Check the Ollama server logs for details."
        )
        sys.exit(1)

    raw: object = response.json()
    if not isinstance(raw, dict):
        logger.error("Unexpected Ollama /api/tags response shape")
        print(
            "ERROR: Unexpected response format from Ollama /api/tags.\n"
            "  Ensure you are running a supported Ollama version."
        )
        sys.exit(1)

    return raw


def _assert_model_available(
    model_name: str,
    available: set[str],
    base_names: set[str],
    *,
    pull_hint: str,
) -> None:
    """Exit with a clear message if *model_name* is not loaded in Ollama.

    Matching is done on both the full name (e.g. ``qwen3:14b``) and the base
    name (e.g. ``qwen3``) to accommodate quantised variants such as
    ``qwen3:14b-instruct-q4_K_M``.
    """
    base = model_name.split(":")[0]
    if model_name not in available and base not in base_names:
        logger.error("Required model '{}' not found in Ollama", model_name)
        print(
            f"ERROR: Model '{model_name}' is not loaded in Ollama.\n"
            f"  Pull it with:  {pull_hint}\n"
            "  Then verify:   ollama list"
        )
        sys.exit(1)
