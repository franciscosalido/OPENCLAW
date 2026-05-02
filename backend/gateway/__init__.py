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
    DEFAULT_EMBED_BACKOFF_SECONDS,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBED_MAX_CONCURRENCY,
    DEFAULT_EMBED_MAX_RETRIES,
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
from backend.gateway.routing_policy import (
    DEFAULT_RAG_CONFIG_PATH,
    RemoteEscalationPolicy,
    RouteBlockReason,
    RouteDecisionKind,
    RouterDecision,
    RoutingDecisionLogger,
    TaskRiskLevel,
    TokenBudgetAccumulator,
    TokenBudgetClass,
    TokenEconomyRecord,
    build_token_economy_record,
    decide_route,
    estimate_prompt_tokens,
    load_routing_policy,
)

__all__ = [
    # Config
    "DEFAULT_LLM_BASE_URL",
    "DEFAULT_LLM_EMBED_MODEL",
    "DEFAULT_LLM_JSON_MODEL",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_LLM_RAG_MODEL",
    "DEFAULT_LLM_REASONING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "DEFAULT_EMBED_BACKOFF_SECONDS",
    "DEFAULT_EMBED_MAX_CONCURRENCY",
    "DEFAULT_EMBED_MAX_RETRIES",
    "ENV_LLM_EMBED_MODEL",
    "GatewayChatClient",
    "GatewayConfig",
    "GatewayEmbedClient",
    "GatewayRuntimeConfig",
    "load_gateway_config",
    # Health
    "check_gateway_services",
    "check_litellm_gateway",
    # Gateway-1 routing policy
    "DEFAULT_RAG_CONFIG_PATH",
    "RemoteEscalationPolicy",
    "RouteBlockReason",
    "RouteDecisionKind",
    "RouterDecision",
    "RoutingDecisionLogger",
    "TaskRiskLevel",
    "TokenBudgetAccumulator",
    "TokenBudgetClass",
    "TokenEconomyRecord",
    "build_token_economy_record",
    "decide_route",
    "estimate_prompt_tokens",
    "load_routing_policy",
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
