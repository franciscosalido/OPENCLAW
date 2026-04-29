"""Gateway configuration schema and loader for LiteLLM alias config.

Validates ``config/litellm_config.yaml`` at load time so a misconfigured
alias fails immediately — with a clear error — rather than at the runtime
model-call boundary.

Usage::

    from backend.gateway.config import load_gateway_config

    cfg = load_gateway_config("config/litellm_config.yaml")
    alias = cfg.get_alias("local_chat")
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.gateway.errors import GatewayConfigurationError, GatewayModelAliasError

# ─── Contract constants ───────────────────────────────────────────────────────

#: All semantic aliases must be present in every valid gateway config.
REQUIRED_ALIASES: frozenset[str] = frozenset(
    {
        "local_chat",
        "local_think",
        "local_rag",
        "local_json",
        "quimera_embed",
        "local_embed",
    }
)

#: Permitted ``api_base`` prefixes. Any other prefix is treated as a remote
#: provider and is rejected by :class:`LiteLLMParams`.
ALLOWED_LOCAL_PREFIXES: tuple[str, ...] = (
    "http://localhost:",
    "http://127.0.0.1:",
)


# ─── Schema models ────────────────────────────────────────────────────────────


class LiteLLMParams(BaseModel):
    """Parameters forwarded verbatim to the LiteLLM router for one alias."""

    model_config = ConfigDict(extra="ignore")

    model: str
    api_base: str
    timeout: int

    @field_validator("api_base")
    @classmethod
    def must_be_local(cls, v: str) -> str:
        """Reject any ``api_base`` that is not a loopback address.

        This enforces the Gateway-0 local-only policy at schema validation
        time rather than at runtime.
        """
        if not any(v.startswith(prefix) for prefix in ALLOWED_LOCAL_PREFIXES):
            raise ValueError(
                f"api_base '{v}' points to a remote host. "
                "Remote providers are not permitted in Gateway-0. "
                "Add remote aliases only after explicit sanitisation approval."
            )
        return v

    @field_validator("timeout")
    @classmethod
    def timeout_must_be_positive(cls, v: int) -> int:
        """Reject invalid LiteLLM alias timeout values."""
        if v <= 0:
            raise ValueError("timeout must be greater than zero")
        return v


class ModelInfo(BaseModel):
    """Semantic metadata attached to a gateway alias.

    ``thinking_mode`` is the contract field that will drive the future
    adapter: when ``True`` the adapter must inject ``/think`` into the
    prompt before dispatching to Qwen3 via Ollama.
    """

    model_config = ConfigDict(extra="ignore")

    provider: str
    purpose: str
    thinking_mode: bool = False
    response_contract: str | None = None
    output_dimensions: int | None = None


class GatewayAlias(BaseModel):
    """One named alias entry in the LiteLLM ``model_list``."""

    model_config = ConfigDict(extra="ignore")

    model_name: str
    litellm_params: LiteLLMParams
    model_info: ModelInfo


class LiteLLMSettings(BaseModel):
    """Top-level LiteLLM global settings block."""

    model_config = ConfigDict(extra="ignore")

    drop_params: bool = True
    set_verbose: bool = False


class GatewayConfig(BaseModel):
    """Validated representation of ``litellm_config.yaml``.

    Raises ``ValueError`` (wrapped by :func:`load_gateway_config` into
    :class:`~backend.gateway.errors.GatewayConfigurationError`) if any
    required alias is absent or any alias resolves to a remote provider.
    """

    model_config = ConfigDict(extra="ignore")

    model_list: list[GatewayAlias]
    litellm_settings: LiteLLMSettings = LiteLLMSettings()

    @model_validator(mode="after")
    def required_aliases_present(self) -> "GatewayConfig":
        """Fail at load time if a required alias is missing from the config."""
        names = {alias.model_name for alias in self.model_list}
        missing = sorted(REQUIRED_ALIASES - names)
        if missing:
            raise ValueError(
                f"Gateway config is missing required aliases: {missing}. "
                "All semantic aliases must be defined before wiring."
            )
        return self

    # ── Accessors ──────────────────────────────────────────────────────────

    def get_alias(self, name: str) -> GatewayAlias:
        """Return the alias named *name*.

        Raises:
            GatewayModelAliasError: if *name* is not defined in the config.
        """
        for alias in self.model_list:
            if alias.model_name == name:
                return alias
        raise GatewayModelAliasError(
            f"Unknown gateway alias: {name!r}", alias=name
        )

    @property
    def alias_names(self) -> set[str]:
        """Return the set of all defined alias names."""
        return {alias.model_name for alias in self.model_list}


# ─── Loader ───────────────────────────────────────────────────────────────────


def load_gateway_config(path: Path | str) -> GatewayConfig:
    """Load and validate *path* as a ``GatewayConfig``.

    Args:
        path: Path to ``litellm_config.yaml``.

    Returns:
        A fully validated :class:`GatewayConfig` instance.

    Raises:
        GatewayConfigurationError: if the file is missing, cannot be parsed
            as YAML, or fails schema validation (e.g. missing alias, remote
            ``api_base``).
    """
    config_path = Path(path)

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise GatewayConfigurationError(
            f"Gateway config file not found: {config_path}"
        ) from exc
    except OSError as exc:
        raise GatewayConfigurationError(
            f"Gateway config file could not be read: {exc}"
        ) from exc

    try:
        raw: object = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise GatewayConfigurationError(
            f"Gateway config YAML parse error in {config_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise GatewayConfigurationError(
            f"Gateway config is not a YAML mapping: {config_path}"
        )

    try:
        return GatewayConfig.model_validate(cast("dict[str, object]", raw))
    except Exception as exc:  # pydantic ValidationError or GatewayModelAliasError
        raise GatewayConfigurationError(
            f"Gateway config validation failed: {exc}"
        ) from exc
