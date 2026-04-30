"""Factory for controlled RAG embedding backends."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml

from backend.gateway.client import GatewayRuntimeConfig
from backend.gateway.embed_client import GatewayEmbedClient
from backend.rag.embeddings import OllamaEmbedder


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"
ENV_RAG_EMBEDDING_BACKEND = "QUIMERA_RAG_EMBEDDING_BACKEND"
BACKEND_GATEWAY_LITELLM = "gateway_litellm"
BACKEND_DIRECT_OLLAMA = "direct_ollama"
ALLOWED_EMBEDDING_BACKENDS = frozenset(
    {BACKEND_GATEWAY_LITELLM, BACKEND_DIRECT_OLLAMA}
)


class RagEmbedder(Protocol):
    """Minimal async embedding interface required by RAG ingestion/retrieval."""

    async def embed(self, text: str) -> list[float]:
        """Embed one text string."""
        ...

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of text strings."""
        ...


@dataclass(frozen=True)
class RagEmbeddingConfig:
    """Controlled RAG embedding backend configuration."""

    active_backend: str
    embedding_alias: str
    legacy_embedding_backend: str
    embedding_model: str
    endpoint: str
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float
    max_concurrency: int
    expected_dimensions: int

    def validated(self) -> RagEmbeddingConfig:
        """Return a validated copy or raise ``ValueError``."""
        active_backend = self.active_backend.strip()
        if active_backend not in ALLOWED_EMBEDDING_BACKENDS:
            raise ValueError(
                "rag.embedding.active_backend must be one of "
                f"{sorted(ALLOWED_EMBEDDING_BACKENDS)}; got {active_backend!r}"
            )
        if not self.embedding_alias.strip():
            raise ValueError("rag.embedding.embedding_alias cannot be empty")
        if self.legacy_embedding_backend.strip() != BACKEND_DIRECT_OLLAMA:
            raise ValueError("rag.embedding.legacy_embedding_backend must be direct_ollama")
        if not self.embedding_model.strip():
            raise ValueError("rag.embedding.embedding_model cannot be empty")
        if not self.endpoint.strip():
            raise ValueError("rag.embedding.endpoint cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("rag.embedding.timeout_seconds must be greater than zero")
        if self.max_retries < 0:
            raise ValueError("rag.embedding.max_retries cannot be negative")
        if self.backoff_seconds < 0:
            raise ValueError("rag.embedding.backoff_seconds cannot be negative")
        if self.max_concurrency <= 0:
            raise ValueError("rag.embedding.max_concurrency must be greater than zero")
        if self.expected_dimensions <= 0:
            raise ValueError("rag.embedding.expected_dimensions must be greater than zero")

        return RagEmbeddingConfig(
            active_backend=active_backend,
            embedding_alias=self.embedding_alias.strip(),
            legacy_embedding_backend=self.legacy_embedding_backend.strip(),
            embedding_model=self.embedding_model.strip(),
            endpoint=self.endpoint.rstrip("/"),
            timeout_seconds=float(self.timeout_seconds),
            max_retries=int(self.max_retries),
            backoff_seconds=float(self.backoff_seconds),
            max_concurrency=int(self.max_concurrency),
            expected_dimensions=int(self.expected_dimensions),
        )


def load_rag_embedding_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
    *,
    env: Mapping[str, str] | None = None,
) -> RagEmbeddingConfig:
    """Load the controlled RAG embedding config from YAML plus env override."""
    values = os.environ if env is None else env
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")
    embedding = rag.get("embedding")
    if not isinstance(embedding, Mapping):
        raise ValueError("rag_config.yaml must contain rag.embedding mapping")

    active_backend = values.get(
        ENV_RAG_EMBEDDING_BACKEND,
        _string_value(embedding, "active_backend", BACKEND_GATEWAY_LITELLM),
    )
    return RagEmbeddingConfig(
        active_backend=active_backend,
        embedding_alias=_string_value(embedding, "embedding_alias", "quimera_embed"),
        legacy_embedding_backend=_string_value(
            embedding,
            "legacy_embedding_backend",
            BACKEND_DIRECT_OLLAMA,
        ),
        embedding_model=_string_value(embedding, "embedding_model", "nomic-embed-text"),
        endpoint=_string_value(embedding, "endpoint", "http://localhost:11434"),
        timeout_seconds=_float_value(embedding, "timeout_seconds", 30.0),
        max_retries=_int_value(embedding, "max_retries", 3),
        backoff_seconds=_float_value(embedding, "backoff_seconds", 1.0),
        max_concurrency=_int_value(embedding, "max_concurrency", 4),
        expected_dimensions=_int_value(embedding, "expected_dimensions", 768),
    ).validated()


def create_rag_embedder(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
    *,
    env: Mapping[str, str] | None = None,
    gateway_http_client: httpx.AsyncClient | None = None,
    ollama_http_client: httpx.AsyncClient | None = None,
) -> RagEmbedder:
    """Create the configured RAG embedder without touching vector stores."""
    config = load_rag_embedding_config(config_path, env=env)
    if config.active_backend == BACKEND_GATEWAY_LITELLM:
        return GatewayEmbedClient(
            config=GatewayRuntimeConfig.from_env(env).validated(),
            model=config.embedding_alias,
            expected_dimensions=config.expected_dimensions,
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
            max_concurrency=config.max_concurrency,
            client=gateway_http_client,
        )
    if config.active_backend == BACKEND_DIRECT_OLLAMA:
        return OllamaEmbedder(
            model=config.embedding_model,
            base_url=config.endpoint,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
            max_concurrency=config.max_concurrency,
            expected_dimensions=config.expected_dimensions,
            client=ollama_http_client,
        )
    raise ValueError(f"Unsupported RAG embedding backend: {config.active_backend}")


def _string_value(data: Mapping[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"rag.embedding.{key} must be a string")
    return value


def _int_value(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"rag.embedding.{key} must be an integer")
    return int(value)


def _float_value(data: Mapping[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"rag.embedding.{key} must be numeric")
    return float(value)
