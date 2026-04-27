"""Domain exceptions for the Quimera/OpenClaw model gateway.

These exceptions intentionally do not depend on LiteLLM internals. Gateway
callers should catch local domain errors, while adapter code can translate
provider-specific exceptions at the boundary.
"""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for local model gateway failures."""

    def __init__(
        self,
        message: str,
        *,
        alias: str | None = None,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.alias = alias
        self.provider = provider

    def to_log_context(self) -> dict[str, str]:
        """Return non-sensitive structured metadata for logs."""
        context: dict[str, str] = {}
        if self.alias is not None:
            context["alias"] = self.alias
        if self.provider is not None:
            context["provider"] = self.provider
        return context


class GatewayConfigurationError(GatewayError):
    """Gateway configuration is missing, invalid, or unsafe."""


class GatewayModelAliasError(GatewayError):
    """A semantic model alias is missing or cannot be resolved."""


class GatewayConnectionError(GatewayError):
    """The local gateway could not be reached."""


class GatewayAuthenticationError(GatewayError):
    """Gateway authentication failed or the API key is missing."""


class GatewayProviderUnavailableError(GatewayError):
    """A configured local provider is unavailable."""


class GatewayRequestRejectedError(GatewayError):
    """A request was rejected before provider execution."""


class GatewayResponseError(GatewayError):
    """A provider response was malformed or unusable."""


class GatewayTimeoutError(GatewayError):
    """A provider call exceeded the configured timeout."""
