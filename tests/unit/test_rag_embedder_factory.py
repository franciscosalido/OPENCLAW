from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import httpx

from backend.gateway.embed_client import GatewayEmbedClient
from backend.rag.embedder_factory import (
    BACKEND_DIRECT_OLLAMA,
    BACKEND_GATEWAY_LITELLM,
    ENV_RAG_EMBEDDING_BACKEND,
    create_rag_embedder,
    load_rag_embedding_config,
)
from backend.rag.embeddings import OllamaEmbedder


class RagEmbedderFactoryTests(unittest.IsolatedAsyncioTestCase):
    def test_loads_gateway_litellm_as_default_backend(self) -> None:
        path = _write_config(active_backend=BACKEND_GATEWAY_LITELLM)

        config = load_rag_embedding_config(path, env={})

        self.assertEqual(config.active_backend, BACKEND_GATEWAY_LITELLM)
        self.assertEqual(config.embedding_alias, "quimera_embed")
        self.assertEqual(config.legacy_embedding_backend, BACKEND_DIRECT_OLLAMA)
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.backoff_seconds, 1.0)
        self.assertEqual(config.max_concurrency, 4)
        self.assertEqual(config.expected_dimensions, 768)

    async def test_factory_returns_gateway_embedder_for_gateway_backend(self) -> None:
        path = _write_config(active_backend=BACKEND_GATEWAY_LITELLM)
        client = httpx.AsyncClient(
            base_url="http://127.0.0.1:4000/v1",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        )
        self.addAsyncCleanup(client.aclose)

        embedder = create_rag_embedder(
            path,
            env={"QUIMERA_LLM_API_KEY": "dev-key"},
            gateway_http_client=client,
        )

        self.assertIsInstance(embedder, GatewayEmbedClient)
        assert isinstance(embedder, GatewayEmbedClient)
        gateway = embedder
        self.assertEqual(gateway.model, "quimera_embed")
        self.assertEqual(gateway.max_retries, 3)
        self.assertEqual(gateway.backoff_seconds, 1.0)
        self.assertEqual(gateway.max_concurrency, 4)

    async def test_factory_returns_ollama_embedder_for_direct_backend(self) -> None:
        path = _write_config(active_backend=BACKEND_DIRECT_OLLAMA)
        client = httpx.AsyncClient(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        )
        self.addAsyncCleanup(client.aclose)

        embedder = create_rag_embedder(
            path,
            env={},
            ollama_http_client=client,
        )

        self.assertIsInstance(embedder, OllamaEmbedder)
        assert isinstance(embedder, OllamaEmbedder)
        ollama = embedder
        self.assertEqual(ollama.model, "nomic-embed-text")
        self.assertEqual(ollama.base_url, "http://localhost:11434")
        self.assertEqual(ollama.max_retries, 3)
        self.assertEqual(ollama.backoff_seconds, 1.0)
        self.assertEqual(ollama.max_concurrency, 4)

    def test_env_override_can_select_direct_ollama_rollback(self) -> None:
        path = _write_config(active_backend=BACKEND_GATEWAY_LITELLM)

        config = load_rag_embedding_config(
            path,
            env={ENV_RAG_EMBEDDING_BACKEND: BACKEND_DIRECT_OLLAMA},
        )

        self.assertEqual(config.active_backend, BACKEND_DIRECT_OLLAMA)

    def test_invalid_backend_raises_clear_error(self) -> None:
        path = _write_config(active_backend="remote_magic")

        with self.assertRaisesRegex(ValueError, "active_backend"):
            load_rag_embedding_config(path, env={})


def _write_config(*, active_backend: str) -> Path:
    text = f"""
rag:
  embedding:
    active_backend: "{active_backend}"
    embedding_alias: "quimera_embed"
    legacy_embedding_backend: "direct_ollama"
    embedding_model: "nomic-embed-text"
    endpoint: "http://localhost:11434"
    timeout_seconds: 30
    max_retries: 3
    backoff_seconds: 1.0
    max_concurrency: 4
    expected_dimensions: 768
"""
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    )
    with handle:
        handle.write(text)
    return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
