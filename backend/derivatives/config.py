"""Configuracao de processo do Laboratorio de Derivativos (Fase 1).

Segue o padrao de ``backend/mcp/mcp_config.py``: dataclass congelada mais
loader com mapa de ambiente injetavel. Nada aqui abre rede; o modo live e
bloqueado por construcao enquanto a Fase 1 nao for homologada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from backend.derivatives.provenance import Readiness

DerivContext = Literal["test", "prod"]
ProviderMode = Literal["offline_fixture", "live_homologated"]

_VALID_CONTEXTS: tuple[str, ...] = ("test", "prod")
_VALID_PROVIDER_MODES: tuple[str, ...] = ("offline_fixture", "live_homologated")


class DerivativesConfigError(ValueError):
    """Erro de configuracao do Laboratorio de Derivativos."""


@dataclass(frozen=True, slots=True)
class DerivativesMcpConfig:
    """Configuracao de processo do servidor MCP ``quimera-derivatives``."""

    host: str = "127.0.0.1"
    port: int = 8814
    path: str = "/mcp"
    context: DerivContext = "prod"
    provider_mode: ProviderMode = "offline_fixture"
    readiness: Readiness = Readiness.A_OFFLINE_VERIFIED


def load_derivatives_mcp_config(
    env: dict[str, str] | None = None,
) -> DerivativesMcpConfig:
    """Carrega a configuracao de processo a partir do ambiente (injetavel).

    Raises:
        DerivativesConfigError: contexto/porta invalidos ou tentativa de
            ``live_homologated``, que permanece bloqueado na Fase 1.
    """
    env_map = os.environ if env is None else env
    context_raw = env_map.get("QUIMERA_DERIV_CONTEXT", "prod")
    if context_raw not in _VALID_CONTEXTS:
        raise DerivativesConfigError(f"QUIMERA_DERIV_CONTEXT invalido: {context_raw!r}")
    mode_raw = env_map.get("QUIMERA_DERIV_PROVIDER_MODE", "offline_fixture")
    if mode_raw not in _VALID_PROVIDER_MODES:
        raise DerivativesConfigError(
            f"QUIMERA_DERIV_PROVIDER_MODE invalido: {mode_raw!r}"
        )
    if mode_raw == "live_homologated":
        raise DerivativesConfigError("live provider not homologated in phase 1")
    port_raw = env_map.get("QUIMERA_DERIV_MCP_PORT", "8814")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise DerivativesConfigError(
            f"QUIMERA_DERIV_MCP_PORT invalido: {port_raw!r}"
        ) from exc
    if not 1 <= port <= 65535:
        raise DerivativesConfigError(
            f"QUIMERA_DERIV_MCP_PORT fora do intervalo: {port}"
        )
    return DerivativesMcpConfig(
        port=port,
        context=cast("DerivContext", context_raw),
        provider_mode=cast("ProviderMode", mode_raw),
    )


def forbid_network(env: dict[str, str] | None = None) -> bool:
    """Indica se o transporte HTTP deve lancar se invocado (CS2; DL-PR04)."""
    env_map = os.environ if env is None else env
    return env_map.get("QUIMERA_DERIV_FORBID_NETWORK") == "1"
