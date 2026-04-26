from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import httpx

from backend.rag import health


class HealthCheckTests(unittest.TestCase):
    def test_check_local_services_passes_when_services_are_available(self) -> None:
        with patch("backend.rag.health.httpx.get", side_effect=_healthy_response):
            health.check_local_services()

    def test_check_local_services_exits_when_qdrant_is_down(self) -> None:
        def failing_qdrant(url: str, timeout: float) -> httpx.Response:
            if url == health.QDRANT_HEALTHZ_URL:
                raise httpx.ConnectError("down")
            return _healthy_response(url, timeout)

        output = io.StringIO()
        with patch("backend.rag.health.httpx.get", side_effect=failing_qdrant):
            with redirect_stdout(output):
                with self.assertRaises(SystemExit) as ctx:
                    health.check_local_services()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Qdrant nao esta acessivel", output.getvalue())

    def test_check_local_services_exits_when_embed_model_is_missing(self) -> None:
        def missing_embedder(url: str, timeout: float) -> httpx.Response:
            if url == health.OLLAMA_TAGS_URL:
                return httpx.Response(
                    200,
                    json={"models": [{"name": "qwen3:14b"}]},
                    request=httpx.Request("GET", url),
                )
            return _healthy_response(url, timeout)

        output = io.StringIO()
        with patch("backend.rag.health.httpx.get", side_effect=missing_embedder):
            with redirect_stdout(output):
                with self.assertRaises(SystemExit) as ctx:
                    health.check_local_services()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("nomic-embed-text", output.getvalue())

    def test_check_local_services_can_skip_qdrant_and_embedder(self) -> None:
        with patch("backend.rag.health.httpx.get") as mocked_get:
            health.check_local_services(require_qdrant=False, require_embedder=False)

        mocked_get.assert_not_called()


def _healthy_response(url: str, timeout: float) -> httpx.Response:
    _ = timeout
    if url == health.QDRANT_HEALTHZ_URL:
        return httpx.Response(200, text="ok", request=httpx.Request("GET", url))
    if url == health.OLLAMA_TAGS_URL:
        return httpx.Response(
            200,
            json={"models": [{"name": health.REQUIRED_EMBEDDING_MODEL}]},
            request=httpx.Request("GET", url),
        )
    raise AssertionError(f"unexpected url: {url}")


if __name__ == "__main__":
    unittest.main()
