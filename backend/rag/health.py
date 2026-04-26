"""Health checks for local RAG services.

Used by CLI scripts to provide actionable operator guidance when Qdrant or
Ollama are unavailable before attempting async operations.

This module uses synchronous httpx by design: preflight runs before the
async event loop starts, so sync HTTP is simpler and correct here.
"""

from __future__ import annotations

import sys

import httpx


QDRANT_HEALTHZ_URL = "http://localhost:6333/healthz"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
REQUIRED_EMBEDDING_MODEL = "nomic-embed-text"
PREFLIGHT_TIMEOUT_SECONDS = 3.0

_QDRANT_HINT = (
    "  Qdrant nao esta acessivel em localhost:6333.\n"
    "  Para iniciar:\n"
    "    docker compose -f docker/docker-compose.qdrant.yml up -d\n"
    "  Para verificar:\n"
    "    curl -fsS http://localhost:6333/healthz"
)
_OLLAMA_HINT = (
    "  Ollama nao esta acessivel em localhost:11434.\n"
    "  Para iniciar:\n"
    "    ollama serve\n"
    "  Para verificar:\n"
    "    curl -fsS http://localhost:11434/api/tags"
)
_EMBEDDING_MODEL_HINT = (
    f"  Modelo '{REQUIRED_EMBEDDING_MODEL}' nao encontrado no Ollama.\n"
    f"  Para baixar:\n"
    f"    ollama pull {REQUIRED_EMBEDDING_MODEL}\n"
    "  Para verificar:\n"
    "    ollama list"
)


def check_local_services(
    *,
    require_qdrant: bool = True,
    require_embedder: bool = True,
) -> None:
    """Check local service availability and exit with code 1 if unavailable.

    Prints actionable setup instructions for each missing service.
    Call from CLI entry points before starting any async operations.

    Args:
        require_qdrant: Check Qdrant healthz endpoint.
        require_embedder: Check Ollama tags and embedding model availability.
    """
    errors: list[str] = []

    if require_qdrant:
        try:
            response = httpx.get(QDRANT_HEALTHZ_URL, timeout=PREFLIGHT_TIMEOUT_SECONDS)
            response.raise_for_status()
        except Exception:
            errors.append(_QDRANT_HINT)

    if require_embedder:
        try:
            response = httpx.get(OLLAMA_TAGS_URL, timeout=PREFLIGHT_TIMEOUT_SECONDS)
            response.raise_for_status()
            body = response.json()
            names = [model.get("name", "") for model in body.get("models", [])]
            if not any(REQUIRED_EMBEDDING_MODEL in name for name in names):
                errors.append(_EMBEDDING_MODEL_HINT)
        except Exception:
            errors.append(_OLLAMA_HINT)

    if not errors:
        return

    print("ERRO: Servicos locais necessarios nao estao disponiveis.\n")
    for error in errors:
        print(error)
        print()
    sys.exit(1)
