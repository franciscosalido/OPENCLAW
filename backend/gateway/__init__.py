"""Gateway contracts for Quimera/OpenClaw model routing.

Runtime chat calls route through the local LiteLLM gateway. Gateway-0 establishes:

* Domain exceptions (errors.py) — stable error taxonomy isolated from LiteLLM
  internals.
* Configuration schema (config.py) — Pydantic validation of
  litellm_config.yaml; rejects remote providers and missing aliases at load
  time.
* Semantic health checks (health.py) — verifies Ollama is running *and* the
  required models are loaded, not just that the HTTP port is open.
"""

from backend.gateway.client import (
    COMPAT_LLM_EMBED_MODEL,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_EMBED_MODEL,
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    DEFAULT_LLM_REASONING_MODEL,
    GatewayChatClient,
    GatewayRuntimeConfig,
)
from backend.gateway.config import GatewayConfig, load_gateway_config
from backend.gateway.embed_client import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    ENV_LLM_EMBED_MODEL,
    GatewayEmbedClient,
)
from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayConfigurationError,
    GatewayError,
    GatewayModelAliasError,
    GatewayProviderUnavailableError,
    GatewayRequestRejectedError,
    GatewayResponseError,
    GatewayTimeoutError,
)
from backend.gateway.health import check_gateway_services, check_litellm_gateway

__all__ = [
    # Config
    "COMPAT_LLM_EMBED_MODEL",
    "DEFAULT_LLM_BASE_URL",
    "DEFAULT_LLM_EMBED_MODEL",
    "DEFAULT_LLM_JSON_MODEL",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_LLM_RAG_MODEL",
    "DEFAULT_LLM_REASONING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "ENV_LLM_EMBED_MODEL",
    "GatewayChatClient",
    "GatewayConfig",
    "GatewayEmbedClient",
    "GatewayRuntimeConfig",
    "load_gateway_config",
    # Health
    "check_gateway_services",
    "check_litellm_gateway",
    # Errors
    "GatewayAuthenticationError",
    "GatewayConnectionError",
    "GatewayConfigurationError",
    "GatewayError",
    "GatewayModelAliasError",
    "GatewayProviderUnavailableError",
    "GatewayRequestRejectedError",
    "GatewayResponseError",
    "GatewayTimeoutError",
]
