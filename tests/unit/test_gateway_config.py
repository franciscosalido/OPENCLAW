"""Contract and schema tests for backend.gateway.config.

Two test classes:

* ``TestGatewaySchema`` — pure schema-level unit tests; no filesystem access.
* ``TestActualGatewayConfig`` — contract tests that load the real
  ``config/litellm_config.yaml`` and assert the structural invariants that
  the runtime wiring adapter will depend on.

If any test in ``TestActualGatewayConfig`` fails, the YAML was changed in a
way that breaks the gateway contract and the PR must not merge.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.gateway.config import (
    REQUIRED_ALIASES,
    GatewayConfig,
    LiteLLMParams,
    LiteLLMSettings,
    load_gateway_config,
)
from backend.gateway.errors import GatewayConfigurationError, GatewayModelAliasError

# ─── Fixtures ─────────────────────────────────────────────────────────────────

_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "litellm_config.yaml"

_LOCALHOST = "http://localhost:11434"
_LOOPBACK = "http://127.0.0.1:11434"
_REMOTE = "https://api.openai.com"

GatewayAliasRaw = dict[str, Any]


def _alias(
    name: str,
    *,
    api_base: str = _LOCALHOST,
    model: str = "ollama_chat/qwen3:14b",
    timeout: int = 60,
    thinking_mode: bool = False,
) -> GatewayAliasRaw:
    return {
        "model_name": name,
        "litellm_params": {"model": model, "api_base": api_base, "timeout": timeout},
        "model_info": {
            "provider": "ollama",
            "purpose": "test",
            "thinking_mode": thinking_mode,
        },
    }


def _all_required_aliases(**overrides: Any) -> list[GatewayAliasRaw]:
    """Return one dict per required alias, applying *overrides* to every entry."""
    return [_alias(name, **overrides) for name in sorted(REQUIRED_ALIASES)]


# ─── Schema unit tests ────────────────────────────────────────────────────────


class TestLiteLLMParamsValidator(unittest.TestCase):
    """Unit tests for the LiteLLMParams field validator."""

    def test_localhost_api_base_accepted(self) -> None:
        params = LiteLLMParams(
            model="ollama_chat/qwen3:14b", api_base=_LOCALHOST, timeout=60
        )
        self.assertEqual(params.api_base, _LOCALHOST)

    def test_loopback_ip_accepted(self) -> None:
        params = LiteLLMParams(
            model="ollama_chat/qwen3:14b", api_base=_LOOPBACK, timeout=60
        )
        self.assertEqual(params.api_base, _LOOPBACK)

    def test_remote_api_base_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            LiteLLMParams(model="gpt-4", api_base=_REMOTE, timeout=60)
        self.assertIn("remote host", str(ctx.exception))

    def test_timeout_must_be_positive(self) -> None:
        for timeout in (0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValidationError) as ctx:
                    LiteLLMParams(
                        model="ollama_chat/qwen3:14b",
                        api_base=_LOCALHOST,
                        timeout=timeout,
                    )
                self.assertIn("greater than zero", str(ctx.exception))

    def test_https_localhost_rejected(self) -> None:
        """TLS termination proxy on localhost is also out of Gateway-0 scope."""
        with self.assertRaises(ValidationError):
            LiteLLMParams(
                model="local", api_base="https://localhost:11434", timeout=60
            )


class TestGatewayConfigValidator(unittest.TestCase):
    """Unit tests for GatewayConfig model-level validation."""

    def test_all_required_aliases_accepted(self) -> None:
        raw = {"model_list": _all_required_aliases()}
        config = GatewayConfig.model_validate(raw)
        self.assertEqual(config.alias_names, REQUIRED_ALIASES)

    def test_missing_single_alias_rejected(self) -> None:
        aliases = [
            _alias(name)
            for name in REQUIRED_ALIASES
            if name != "local_embed"
        ]
        with self.assertRaises(ValidationError) as ctx:
            GatewayConfig.model_validate({"model_list": aliases})
        self.assertIn("local_embed", str(ctx.exception))

    def test_missing_multiple_aliases_rejected(self) -> None:
        raw = {"model_list": [_alias("local_chat")]}
        with self.assertRaises(ValidationError) as ctx:
            GatewayConfig.model_validate(raw)
        self.assertIn("missing required aliases", str(ctx.exception))

    def test_extra_alias_permitted(self) -> None:
        """Additional aliases beyond the required five must not cause failures."""
        aliases = _all_required_aliases() + [_alias("local_extra")]
        config = GatewayConfig.model_validate({"model_list": aliases})
        self.assertIn("local_extra", config.alias_names)

    def test_get_alias_returns_correct_entry(self) -> None:
        config = GatewayConfig.model_validate({"model_list": _all_required_aliases()})
        alias = config.get_alias("local_chat")
        self.assertEqual(alias.model_name, "local_chat")

    def test_get_alias_raises_for_unknown_name(self) -> None:
        config = GatewayConfig.model_validate({"model_list": _all_required_aliases()})
        with self.assertRaises(GatewayModelAliasError):
            config.get_alias("does_not_exist")

    def test_default_litellm_settings_applied(self) -> None:
        config = GatewayConfig.model_validate({"model_list": _all_required_aliases()})
        self.assertTrue(config.litellm_settings.drop_params)
        self.assertFalse(config.litellm_settings.set_verbose)

    def test_remote_api_base_in_any_alias_rejected(self) -> None:
        aliases = _all_required_aliases()
        aliases[0]["litellm_params"]["api_base"] = _REMOTE
        with self.assertRaises(ValidationError) as ctx:
            GatewayConfig.model_validate({"model_list": aliases})
        self.assertIn("remote host", str(ctx.exception))


class TestLoadGatewayConfigErrors(unittest.TestCase):
    """Unit tests for load_gateway_config error handling."""

    def test_missing_file_raises_gateway_config_error(self) -> None:
        with self.assertRaises(GatewayConfigurationError) as ctx:
            load_gateway_config("/nonexistent/path/litellm_config.yaml")
        self.assertIn("not found", str(ctx.exception))

    def test_invalid_yaml_raises_gateway_config_error(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("model_list: [\n  - broken yaml: [")
            tmp = f.name
        with self.assertRaises(GatewayConfigurationError) as ctx:
            load_gateway_config(tmp)
        self.assertIn("YAML parse error", str(ctx.exception))

    def test_non_mapping_yaml_raises_gateway_config_error(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("- just\n- a list\n")
            tmp = f.name
        with self.assertRaises(GatewayConfigurationError) as ctx:
            load_gateway_config(tmp)
        self.assertIn("not a YAML mapping", str(ctx.exception))


# ─── Contract tests against real litellm_config.yaml ─────────────────────────


class TestActualGatewayConfig(unittest.TestCase):
    """Contract tests that load the real config/litellm_config.yaml.

    These tests define the invariants the wiring adapter will rely on.
    A failing test here means the YAML change broke a gateway contract.
    """

    def setUp(self) -> None:
        self.config = load_gateway_config(_YAML_PATH)

    def test_all_five_required_aliases_present(self) -> None:
        self.assertEqual(
            self.config.alias_names,
            REQUIRED_ALIASES,
            "All five required aliases must be defined in litellm_config.yaml",
        )

    def test_all_aliases_use_local_api_base(self) -> None:
        for alias in self.config.model_list:
            with self.subTest(alias=alias.model_name):
                self.assertTrue(
                    alias.litellm_params.api_base.startswith("http://localhost:"),
                    f"Alias '{alias.model_name}' has non-local api_base: "
                    f"{alias.litellm_params.api_base}",
                )

    def test_local_think_has_thinking_mode_true(self) -> None:
        """Adapter contract: local_think must signal thinking_mode so /think is injected."""
        think = self.config.get_alias("local_think")
        self.assertTrue(
            think.model_info.thinking_mode,
            "local_think.model_info.thinking_mode must be true — "
            "the future wiring adapter reads this field to inject /think",
        )

    def test_non_thinking_aliases_have_thinking_mode_false(self) -> None:
        """Adapter contract: default aliases must NOT inject /think."""
        for name in ("local_chat", "local_rag", "local_json"):
            with self.subTest(alias=name):
                alias = self.config.get_alias(name)
                self.assertFalse(
                    alias.model_info.thinking_mode,
                    f"'{name}' must have thinking_mode=false",
                )

    def test_local_embed_maps_to_nomic_embed_text(self) -> None:
        embed = self.config.get_alias("local_embed")
        self.assertIn(
            "nomic-embed-text",
            embed.litellm_params.model,
            "local_embed must map to the nomic-embed-text model",
        )

    def test_local_chat_maps_to_qwen(self) -> None:
        chat = self.config.get_alias("local_chat")
        self.assertIn(
            "qwen",
            chat.litellm_params.model.lower(),
            "local_chat must map to a Qwen model",
        )

    def test_local_think_uses_longer_timeout(self) -> None:
        """Thinking calls need more wall time than default chat calls."""
        think = self.config.get_alias("local_think")
        chat = self.config.get_alias("local_chat")
        self.assertGreater(
            think.litellm_params.timeout,
            chat.litellm_params.timeout,
            "local_think timeout must exceed local_chat timeout",
        )

    def test_alias_timeouts_match_gateway_runtime_contract(self) -> None:
        expected = {
            "local_chat": 30,
            "local_think": 120,
            "local_rag": 60,
            "local_json": 30,
            "local_embed": 30,
        }
        for name, timeout in expected.items():
            with self.subTest(alias=name):
                alias = self.config.get_alias(name)
                self.assertEqual(alias.litellm_params.timeout, timeout)

    def test_all_alias_timeouts_are_positive(self) -> None:
        for alias in self.config.model_list:
            with self.subTest(alias=alias.model_name):
                self.assertGreater(alias.litellm_params.timeout, 0)

    def test_drop_params_enabled(self) -> None:
        self.assertTrue(
            self.config.litellm_settings.drop_params,
            "drop_params must be enabled to suppress unsupported params silently",
        )

    def test_verbose_disabled(self) -> None:
        self.assertFalse(
            self.config.litellm_settings.set_verbose,
            "set_verbose must be false to keep logs clean in production",
        )

    def test_no_alias_points_to_remote_provider(self) -> None:
        """Security contract: no remote provider may slip into the config."""
        for alias in self.config.model_list:
            with self.subTest(alias=alias.model_name):
                self.assertFalse(
                    alias.litellm_params.api_base.startswith("https://"),
                    f"Alias '{alias.model_name}' unexpectedly points to HTTPS endpoint",
                )
                self.assertNotIn(
                    "openai",
                    alias.litellm_params.api_base.lower(),
                    f"Alias '{alias.model_name}' api_base contains 'openai'",
                )


if __name__ == "__main__":
    unittest.main()
