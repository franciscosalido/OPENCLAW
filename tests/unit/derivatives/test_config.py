"""Contratos de configuracao do Laboratorio de Derivativos (processo + YAML)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.derivatives.config import (
    DerivativesConfigError,
    DerivativesMcpConfig,
    forbid_network,
    load_derivatives_mcp_config,
)
from backend.derivatives.provenance import Readiness
from config.derivatives_config_model import load_derivatives_config


def test_process_config_defaults() -> None:
    config = load_derivatives_mcp_config({})
    assert config == DerivativesMcpConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8814
    assert config.path == "/mcp"
    assert config.context == "prod"
    assert config.provider_mode == "offline_fixture"
    assert config.readiness is Readiness.A_OFFLINE_VERIFIED


def test_process_config_env_injection() -> None:
    config = load_derivatives_mcp_config(
        {"QUIMERA_DERIV_CONTEXT": "test", "QUIMERA_DERIV_MCP_PORT": "9001"}
    )
    assert config.context == "test"
    assert config.port == 9001


def test_live_provider_mode_is_hard_blocked() -> None:
    with pytest.raises(DerivativesConfigError, match="not homologated"):
        load_derivatives_mcp_config(
            {"QUIMERA_DERIV_PROVIDER_MODE": "live_homologated"}
        )


def test_invalid_context_rejected() -> None:
    with pytest.raises(DerivativesConfigError, match="QUIMERA_DERIV_CONTEXT"):
        load_derivatives_mcp_config({"QUIMERA_DERIV_CONTEXT": "staging"})


def test_invalid_provider_mode_rejected() -> None:
    with pytest.raises(DerivativesConfigError, match="QUIMERA_DERIV_PROVIDER_MODE"):
        load_derivatives_mcp_config({"QUIMERA_DERIV_PROVIDER_MODE": "fixture"})


def test_invalid_port_rejected() -> None:
    with pytest.raises(DerivativesConfigError, match="QUIMERA_DERIV_MCP_PORT"):
        load_derivatives_mcp_config({"QUIMERA_DERIV_MCP_PORT": "oitomil"})
    with pytest.raises(DerivativesConfigError, match="fora do intervalo"):
        load_derivatives_mcp_config({"QUIMERA_DERIV_MCP_PORT": "70000"})


def test_forbid_network_flag() -> None:
    assert forbid_network({"QUIMERA_DERIV_FORBID_NETWORK": "1"}) is True
    assert forbid_network({"QUIMERA_DERIV_FORBID_NETWORK": "0"}) is False
    assert forbid_network({}) is False


def test_default_yaml_loads() -> None:
    config = load_derivatives_config()
    assert config.conventions.day_count == "business_252"
    assert config.conventions.rate_compounding == "annual_exp_252"
    assert config.conventions.rate_compounding_assumed is True
    assert config.budget.per_minute == 100
    assert config.budget.per_second == 50
    assert config.budget.max_retries == 0
    assert str(config.oplab.base_url) == "https://api.oplab.com.br/v3"
    assert len(config.oplab.allowed_routes) == 4
    assert all(route.startswith("/market/") for route in config.oplab.allowed_routes)
    assert config.iv.max_iterations == 200


def test_unknown_yaml_key_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "derivatives.yaml"
    bad.write_text("chave_desconhecida: 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_derivatives_config(bad)


def test_domain_route_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "derivatives.yaml"
    bad.write_text(
        'oplab:\n  allowed_routes:\n    - "/domain/orders"\n', encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="rota proibida"):
        load_derivatives_config(bad)


def test_non_market_route_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "derivatives.yaml"
    bad.write_text(
        'oplab:\n  allowed_routes:\n    - "/account/me"\n', encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="fora de /market/"):
        load_derivatives_config(bad)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "derivatives.yaml"
    bad.write_text("- apenas\n- uma\n- lista\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapeamento YAML"):
        load_derivatives_config(bad)
