"""Unit tests for backend.gateway.health semantic checks.

All Ollama network calls are mocked via unittest.mock.patch so these tests
run without any local service running.

The key invariant under test: check_gateway_services() must exit with
status 1 and a human-readable message whenever:
  - Ollama is not reachable;
  - a required model is missing from the model list;
  - Ollama returns a non-200 status.

It must NOT exit when all required models are present.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from backend.gateway.health import (
    OLLAMA_TAGS_URL,
    REQUIRED_CHAT_MODEL,
    REQUIRED_EMBED_MODEL,
    REQUIRED_GATEWAY_ALIASES,
    check_gateway_services,
    check_litellm_gateway,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _tags_ok(*model_names: str) -> httpx.Response:
    """Return a 200 /api/tags response listing *model_names*."""
    return httpx.Response(
        200,
        json={"models": [{"name": name} for name in model_names]},
        request=httpx.Request("GET", OLLAMA_TAGS_URL),
    )


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    response = httpx.Response(
        status_code,
        request=httpx.Request("GET", OLLAMA_TAGS_URL),
    )
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=response.request, response=response
    )


def _models_ok(*model_names: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"id": name} for name in model_names]},
        request=httpx.Request("GET", "http://127.0.0.1:4000/v1/models"),
    )


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestCheckGatewayServices(unittest.TestCase):
    def test_passes_when_both_models_available(self) -> None:
        """No exit when both chat and embed models are present."""
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(REQUIRED_CHAT_MODEL, REQUIRED_EMBED_MODEL),
        ):
            # Must not raise or call sys.exit.
            check_gateway_services()

    def test_exits_1_when_ollama_unreachable(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services()
            self.assertEqual(ctx.exception.code, 1)

    def test_exits_1_when_chat_model_missing(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(REQUIRED_EMBED_MODEL),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services(require_chat=True, require_embed=False)
            self.assertEqual(ctx.exception.code, 1)

    def test_exits_1_when_embed_model_missing(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(REQUIRED_CHAT_MODEL),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services(require_chat=False, require_embed=True)
            self.assertEqual(ctx.exception.code, 1)

    def test_skips_chat_check_when_not_required(self) -> None:
        """Only embed model present — should not exit if require_chat=False."""
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(REQUIRED_EMBED_MODEL),
        ):
            check_gateway_services(require_chat=False, require_embed=True)

    def test_skips_embed_check_when_not_required(self) -> None:
        """Only chat model present — should not exit if require_embed=False."""
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(REQUIRED_CHAT_MODEL),
        ):
            check_gateway_services(require_chat=True, require_embed=False)

    def test_exits_1_on_http_503(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            side_effect=_http_error(503),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services()
            self.assertEqual(ctx.exception.code, 1)

    def test_accepts_quantised_model_variant(self) -> None:
        """qwen3:14b-instruct-q4_K_M should satisfy REQUIRED_CHAT_MODEL via base match."""
        quantised = f"{REQUIRED_CHAT_MODEL.split(':')[0]}:14b-instruct-q4_K_M"
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=_tags_ok(quantised, REQUIRED_EMBED_MODEL),
        ):
            # Base name 'qwen3' matches the quantised variant — must not exit.
            check_gateway_services()

    def test_exits_when_models_key_is_empty_list(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=httpx.Response(
                200,
                json={"models": []},
                request=httpx.Request("GET", OLLAMA_TAGS_URL),
            ),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services()
            self.assertEqual(ctx.exception.code, 1)

    def test_exits_when_response_is_not_a_dict(self) -> None:
        with patch(
            "backend.gateway.health.httpx.get",
            return_value=httpx.Response(
                200,
                json=["unexpected", "list"],
                request=httpx.Request("GET", OLLAMA_TAGS_URL),
            ),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_gateway_services()
            self.assertEqual(ctx.exception.code, 1)


class TestCheckLiteLLMGateway(unittest.TestCase):
    def test_litellm_gateway_passes_when_aliases_available(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"QUIMERA_LLM_API_KEY": "dev-key"},
                clear=False,
            ),
            patch(
                "backend.gateway.health.httpx.get",
                return_value=_models_ok(*REQUIRED_GATEWAY_ALIASES),
            ),
        ):
            check_litellm_gateway()

    def test_litellm_gateway_exits_when_api_key_missing(self) -> None:
        with patch.dict("os.environ", {"QUIMERA_LLM_API_KEY": ""}, clear=False):
            with self.assertRaises(SystemExit) as ctx:
                check_litellm_gateway()
            self.assertEqual(ctx.exception.code, 1)

    def test_litellm_gateway_exits_when_alias_missing(self) -> None:
        aliases = sorted(REQUIRED_GATEWAY_ALIASES - {"local_json"})
        with (
            patch.dict(
                "os.environ",
                {"QUIMERA_LLM_API_KEY": "dev-key"},
                clear=False,
            ),
            patch(
                "backend.gateway.health.httpx.get",
                return_value=_models_ok(*aliases),
            ),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_litellm_gateway()
            self.assertEqual(ctx.exception.code, 1)

    def test_litellm_gateway_exits_on_auth_failure(self) -> None:
        response = httpx.Response(
            401,
            request=httpx.Request("GET", "http://127.0.0.1:4000/v1/models"),
        )
        with (
            patch.dict(
                "os.environ",
                {"QUIMERA_LLM_API_KEY": "dev-key"},
                clear=False,
            ),
            patch("backend.gateway.health.httpx.get", return_value=response),
        ):
            with self.assertRaises(SystemExit) as ctx:
                check_litellm_gateway()
            self.assertEqual(ctx.exception.code, 1)

if __name__ == "__main__":
    unittest.main()
