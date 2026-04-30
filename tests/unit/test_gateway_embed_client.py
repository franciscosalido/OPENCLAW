from __future__ import annotations

import json
import unittest
from typing import cast

import httpx
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_EMBED_MODEL,
    GatewayRuntimeConfig,
)
from backend.gateway.embed_client import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    GatewayEmbedClient,
)
from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayResponseError,
    GatewayTimeoutError,
)


def _vector(dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> list[float]:
    return [float(index) / 1000.0 for index in range(dimensions)]


def _embedding_response(count: int = 1) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": _vector()}
            for index in range(count)
        ],
    }


class GatewayEmbedClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_embed_single_text_returns_vector(self) -> None:
        seen_payloads: list[dict[str, object]] = []
        seen_auth_headers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            seen_auth_headers.append(request.headers.get("authorization"))
            self.assertEqual(request.url.path, "/v1/embeddings")
            return httpx.Response(200, json=_embedding_response())

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="secret-test-key"),
                client=client,
            )
            vector = await gateway.embed("texto sintetico")

        self.assertEqual(len(vector), DEFAULT_EMBEDDING_DIMENSIONS)
        self.assertEqual(seen_auth_headers, ["Bearer secret-test-key"])
        self.assertEqual(
            seen_payloads,
            [{"model": DEFAULT_LLM_EMBED_MODEL, "input": "texto sintetico"}],
        )

    async def test_embed_batch_returns_vectors(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json=_embedding_response(count=2))

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            vectors = await gateway.embed_batch(["texto um", "texto dois"])

        self.assertEqual(len(vectors), 2)
        self.assertTrue(all(len(vector) == DEFAULT_EMBEDDING_DIMENSIONS for vector in vectors))
        self.assertEqual(
            seen_payloads,
            [
                {
                    "model": DEFAULT_LLM_EMBED_MODEL,
                    "input": ["texto um", "texto dois"],
                }
            ],
        )

    async def test_empty_batch_returns_empty_list_without_http_call(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("HTTP call should not happen for an empty batch")

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            vectors = await gateway.embed_batch([])

        self.assertEqual(vectors, [])

    async def test_wrong_dimension_raises_response_error(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "index": 0,
                                "embedding": _vector(dimensions=767),
                            }
                        ]
                    },
                )
            ),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayResponseError):
                await gateway.embed("texto sintetico")

    async def test_non_numeric_vector_values_are_rejected(self) -> None:
        bad_vector: list[object] = list(_vector())
        bad_vector[0] = "not-a-number"

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={"data": [{"index": 0, "embedding": bad_vector}]},
                )
            ),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayResponseError):
                await gateway.embed("texto sintetico")

    async def test_missing_api_key_fails_clearly(self) -> None:
        # GatewayRuntimeConfig.validated() raises GatewayAuthenticationError
        # before any HTTP client is constructed — no real httpx.AsyncClient needed.
        with self.assertRaises(GatewayAuthenticationError) as ctx:
            GatewayEmbedClient(config=GatewayRuntimeConfig(api_key=None))
        self.assertIn("QUIMERA_LLM_API_KEY", str(ctx.exception))

    async def test_auth_error_maps_to_gateway_authentication_error(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(lambda _request: httpx.Response(401)),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="secret-test-key"),
                client=client,
            )
            with self.assertRaises(GatewayAuthenticationError) as ctx:
                await gateway.embed("texto sintetico")

        self.assertNotIn("secret-test-key", str(ctx.exception))

    async def test_connection_error_maps_to_gateway_connection_error(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayConnectionError):
                await gateway.embed("texto sintetico")

    async def test_timeout_maps_to_gateway_timeout_error(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout")

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayTimeoutError):
                await gateway.embed("texto sintetico")

    async def test_bad_response_shape_maps_to_gateway_response_error(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"data": []})
            ),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayResponseError):
                await gateway.embed("texto sintetico")

    async def test_input_text_and_api_key_are_not_logged(self) -> None:
        logs: list[str] = []
        sink_id = logger.add(
            lambda message: logs.append(str(message)),
            format="{message}",
        )
        try:
            async with httpx.AsyncClient(
                base_url=DEFAULT_LLM_BASE_URL,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json=_embedding_response())
                ),
            ) as client:
                gateway = GatewayEmbedClient(
                    config=GatewayRuntimeConfig(api_key="secret-test-key"),
                    client=client,
                )
                await gateway.embed("texto sintetico que nao deve aparecer")
        finally:
            logger.remove(sink_id)

        joined = "\n".join(logs)
        self.assertIn("gateway_embed", joined)
        self.assertIn("model_alias=quimera_embed", joined)
        self.assertNotIn("secret-test-key", joined)
        self.assertNotIn("texto sintetico que nao deve aparecer", joined)

    async def test_request_timeout_uses_canonical_embed_alias_budget(self) -> None:
        seen_timeouts: list[dict[str, float]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_timeouts.append(cast("dict[str, float]", request.extensions["timeout"]))
            return httpx.Response(200, json=_embedding_response())

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            await gateway.embed("texto sintetico")

        self.assertEqual(seen_timeouts[0]["read"], 30.0)


if __name__ == "__main__":
    unittest.main()
