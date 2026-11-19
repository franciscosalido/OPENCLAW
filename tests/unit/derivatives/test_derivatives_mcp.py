"""DL-PR07: servidor MCP ``quimera-derivatives`` — barreira de procedencia e contexto."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from backend.derivatives.config import (
    DerivativesConfigError,
    DerivativesMcpConfig,
    load_derivatives_mcp_config,
)
from backend.derivatives.mcp.derivatives_server import (
    CHAIN_SCHEMA,
    DEMO_TEST_DATA,
    LIVE_NOT_ACTIVATED,
    SERVER_NAME,
    ProvenanceBarrierError,
    chain_tool,
    create_derivatives_server,
    demo_tool,
    main,
    production_view,
    system_clock,
)
from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.errors import RateLimitedError
from backend.derivatives.oplab.routes import MarketRoute
from backend.derivatives.oplab.transport import FixtureTransport, VendorResponse
from backend.derivatives.pricing.calendar import load_calendars
from backend.derivatives.provenance import Provenance, Purpose, Readiness
from backend.derivatives.service.chain_service import ChainService, PricedChain
from config.derivatives_config_model import load_derivatives_config
from scripts.derivatives_make_synthetic_fixture import VALUATION

SYNTHETIC = Path("tests/fixtures/derivatives/synthetic")
DOCUMENTAL = Path("tests/fixtures/derivatives/documental")
CLOCK_NOW = datetime(2026, 11, 5, 20, 0, 5, tzinfo=UTC)
PROD = DerivativesMcpConfig()
TEST = DerivativesMcpConfig(context="test", fixture_dir=str(SYNTHETIC))
FORGED_LIVE = DerivativesMcpConfig(provider_mode="live_homologated",
                                   readiness=Readiness.C_PROMOTED)
QUOTE_KEYS = {"rows", "spot", "rate", "underlying", "expiry", "row_count", "time_to_expiry"}


def clock() -> datetime:
    return CLOCK_NOW


class ProvenanceTransport:
    """Fixture sintetica com procedencia forcada por rota e contagem de leituras."""

    def __init__(self, overrides: Mapping[MarketRoute, Provenance],
                 fail: Exception | None = None) -> None:
        self.inner = FixtureTransport(SYNTHETIC)
        self.overrides = dict(overrides)
        self.fail = fail
        self.calls = 0

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        response = await self.inner.get(route, params=params, now=now)
        provenance = self.overrides.get(route, response.provenance)
        return VendorResponse(response.status, response.json, response.headers_safe,
                              response.received_at, response.route, provenance)


def _service(transport: object) -> ChainService:
    cfg = load_derivatives_config()
    client = OplabMarketClient(transport, stamp_source="test:")  # type: ignore[arg-type]
    return ChainService(client, cfg=cfg,
                        calendars=load_calendars(cfg.conventions, root=Path.cwd()))


ALL_OBSERVED = {route: Provenance.OBSERVED for route in MarketRoute}


async def _tool_names(server: FastMCP[Any]) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


async def _call(server: FastMCP[Any], name: str, **arguments: str) -> dict[str, Any]:
    async with Client(server) as client:
        result = await client.call_tool(name, arguments)
    data: dict[str, Any] = result.data
    return data


async def test_production_context_exposes_exactly_health_and_chain() -> None:
    server = create_derivatives_server(PROD, clock=clock)
    assert server.name == SERVER_NAME == "quimera-derivatives"
    assert await _tool_names(server) == {"derivatives_health", "derivatives_chain"}


async def test_demo_tool_exists_only_in_test_context() -> None:
    server = create_derivatives_server(TEST, clock=clock)
    assert await _tool_names(server) == {
        "derivatives_health", "derivatives_chain", "derivatives_chain_demo"}
    with pytest.raises(ToolError):
        await _call(create_derivatives_server(PROD, clock=clock),
                    "derivatives_chain_demo", symbol="BOVA11", due_date="2026-11-19")


async def test_context_comes_from_the_process_environment_only() -> None:
    prod = create_derivatives_server(load_derivatives_mcp_config({}), clock=clock)
    test = create_derivatives_server(load_derivatives_mcp_config(
        {"QUIMERA_DERIV_CONTEXT": "test", "QUIMERA_DERIV_FIXTURE_DIR": str(SYNTHETIC)}),
        clock=clock)
    assert "derivatives_chain_demo" not in await _tool_names(prod)
    assert "derivatives_chain_demo" in await _tool_names(test)
    assert load_derivatives_mcp_config({}).fixture_dir is None
    assert load_derivatives_mcp_config({"QUIMERA_DERIV_FIXTURE_DIR": ""}).fixture_dir is None
    with pytest.raises(DerivativesConfigError, match="not homologated"):
        load_derivatives_mcp_config({"QUIMERA_DERIV_PROVIDER_MODE": "live_homologated"})


@pytest.mark.parametrize("config", [PROD, TEST])
async def test_production_tool_answers_live_not_activated_without_quotes(
    config: DerivativesMcpConfig,
) -> None:
    server = create_derivatives_server(config, clock=clock)
    response = await _call(server, "derivatives_chain", symbol="BOVA11",
                           due_date="2026-11-19")
    assert response["ok"] is True and response["degraded"] is True
    assert response["error"] is None
    data = response["data"]
    assert set(data) == {"schema_version", "status", "readiness", "as_of", "message"}
    assert data["status"] == LIVE_NOT_ACTIVATED == "LIVE_NOT_ACTIVATED"
    assert data["readiness"] == "A"
    assert data["schema_version"] == CHAIN_SCHEMA
    assert data["as_of"] == CLOCK_NOW.isoformat()
    assert QUOTE_KEYS.isdisjoint(data)


@pytest.mark.parametrize("extra", ["mode", "allow_fixture", "path", "url", "provider",
                                   "context", "fixture_dir"])
@pytest.mark.parametrize("tool", ["derivatives_chain", "derivatives_chain_demo"])
async def test_tools_reject_any_parameter_outside_the_schema(tool: str, extra: str) -> None:
    server = create_derivatives_server(TEST, clock=clock)
    with pytest.raises(ToolError):
        await _call(server, tool, symbol="BOVA11", due_date="2026-11-19",
                    **{extra: "offline_fixture"})


async def test_tool_schemas_have_exactly_symbol_and_due_date() -> None:
    server = create_derivatives_server(TEST, clock=clock)
    async with Client(server) as client:
        tools = {tool.name: tool.inputSchema for tool in await client.list_tools()}
    for name in ("derivatives_chain", "derivatives_chain_demo"):
        assert set(tools[name]["properties"]) == {"symbol", "due_date"}
        assert tools[name]["additionalProperties"] is False
    assert tools["derivatives_health"]["properties"] == {}


@pytest.mark.parametrize(
    ("symbol", "due_date"),
    [("", "2026-11-19"), ("   ", "2026-11-19"), ("BOVA11/..", "2026-11-19"),
     ("BO", "2026-11-19"), ("BOVA11?x=1", "2026-11-19"), ("BOVA11", ""),
     ("BOVA11", "19/11/2026"), ("BOVA11", "amanha"), ("BOVA11", "2026-13-40")],
)
@pytest.mark.parametrize("tool", ["derivatives_chain", "derivatives_chain_demo"])
async def test_invalid_inputs_return_sanitized_errors_never_exceptions(
    tool: str, symbol: str, due_date: str,
) -> None:
    response = await _call(create_derivatives_server(TEST, clock=clock), tool,
                           symbol=symbol, due_date=due_date)
    assert response["ok"] is False
    assert response["data"] == {}
    assert isinstance(response["error"], str) and 0 < len(response["error"]) <= 240


async def test_lowercase_symbol_is_normalized() -> None:
    response = await _call(create_derivatives_server(TEST, clock=clock),
                           "derivatives_chain_demo", symbol=" bova11 ", due_date="2026-11-19")
    assert response["ok"] is True
    assert response["data"]["underlying"] == "BOVA11"


async def test_demo_serves_the_synthetic_chain_labelled_as_test_data() -> None:
    response = await _call(create_derivatives_server(TEST, clock=clock),
                           "derivatives_chain_demo", symbol="BOVA11", due_date="2026-11-19")
    assert response["ok"] is True and response["degraded"] is True
    data = response["data"]
    assert data["status"] == DEMO_TEST_DATA
    assert (data["purpose"], data["provenance"], data["readiness"]) == (
        "test", "synthetic", "A")
    assert data["as_of"] == VALUATION.isoformat()
    assert data["row_count"] == len(data["rows"]) == 100
    assert data["spot"] == {"price": "150.0", "source": "STOCK_ENDPOINT"}
    assert data["rate"] == {"uid": "SELIC", "value_pct_aa": "14.9"}
    assert data["time_to_expiry"]["business_days"] == 10
    assert data["unpriceable_reason"] is None
    assert "nao pressupoe execucao" in data["price_source_note"]
    assert data["model_assumptions"]["calendar_id"] == "B3_LISTED_TRADING"
    first = data["rows"][0]
    assert set(first) == {"symbol", "kind", "exercise_style", "strike", "bid", "ask", "mid",
                          "last", "supported", "reason", "model_price", "greeks", "iv",
                          "quality_flags", "missing_metadata"}
    assert first["supported"] is True and first["iv"]["mid"]["status"] == "ok"
    assert isinstance(first["bid"], str) and isinstance(first["greeks"]["delta"], float)
    encoded = json.dumps(response)
    assert len(encoded) < 80_000, "visao compacta: resposta deve caber no contexto do agente"


async def test_demo_is_reproducible_and_independent_of_the_clock() -> None:
    first = await demo_tool("BOVA11", "2026-11-19", config=TEST, root=Path.cwd())
    late = create_derivatives_server(
        TEST, clock=lambda: datetime(2030, 1, 1, tzinfo=UTC))
    second = await _call(late, "derivatives_chain_demo", symbol="BOVA11",
                         due_date="2026-11-19")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize(
    "config",
    [DerivativesMcpConfig(context="test"), DerivativesMcpConfig(fixture_dir=str(SYNTHETIC)),
     DerivativesMcpConfig(context="test", fixture_dir=str(DOCUMENTAL)),
     DerivativesMcpConfig(context="test", fixture_dir="/caminho/que/nao/existe")],
)
async def test_demo_refuses_without_test_context_or_valid_fixture(
    config: DerivativesMcpConfig,
) -> None:
    response = await demo_tool("BOVA11", "2026-11-19", config=config, root=Path.cwd())
    assert response["ok"] is False and response["data"] == {}


async def test_demo_unknown_symbol_is_a_sanitized_error() -> None:
    response = await demo_tool("VALE3", "2026-11-19", config=TEST, root=Path.cwd())
    assert response["ok"] is False
    assert "fixture ausente" in str(response["error"])


async def test_fixture_never_reaches_the_production_tool_even_when_forged_live() -> None:
    transport = ProvenanceTransport({})
    response = await chain_tool("BOVA11", "2026-11-19", config=FORGED_LIVE, clock=clock,
                                live_service=_service(transport))
    assert transport.calls == 4
    assert response["ok"] is False and response["data"] == {}
    assert "dado de teste bloqueado" in str(response["error"])
    assert "150" not in json.dumps(response)


@pytest.mark.parametrize("fixture_route", list(MarketRoute))
async def test_a_single_test_read_blocks_the_production_tool(
    fixture_route: MarketRoute,
) -> None:
    overrides = {route: Provenance.OBSERVED for route in MarketRoute if route != fixture_route}
    response = await chain_tool("BOVA11", "2026-11-19", config=FORGED_LIVE, clock=clock,
                                live_service=_service(ProvenanceTransport(overrides)))
    assert response["ok"] is False and response["data"] == {}


async def test_only_fully_observed_data_passes_the_production_barrier() -> None:
    response = await chain_tool("BOVA11", "2026-11-19", config=FORGED_LIVE, clock=clock,
                                live_service=_service(ProvenanceTransport(ALL_OBSERVED)))
    assert response["ok"] is True and response["degraded"] is False
    data = response["data"]
    assert (data["status"], data["purpose"], data["provenance"]) == (
        "OK", "production", "observed")
    assert data["row_count"] == 100 and data["as_of"] == CLOCK_NOW.isoformat()


@pytest.mark.parametrize(
    "config",
    [PROD, DerivativesMcpConfig(readiness=Readiness.C_PROMOTED),
     DerivativesMcpConfig(readiness=Readiness.B_HOMOLOGATED,
                          provider_mode="live_homologated")],
)
async def test_without_full_activation_the_live_service_is_never_called(
    config: DerivativesMcpConfig,
) -> None:
    transport = ProvenanceTransport(ALL_OBSERVED)
    response = await chain_tool("BOVA11", "2026-11-19", config=config, clock=clock,
                                live_service=_service(transport))
    assert transport.calls == 0
    assert response["data"]["status"] == LIVE_NOT_ACTIVATED


async def test_activated_without_live_service_is_still_not_activated() -> None:
    response = await chain_tool("BOVA11", "2026-11-19", config=FORGED_LIVE, clock=clock)
    assert response["data"]["status"] == LIVE_NOT_ACTIVATED


async def test_live_failure_is_an_error_and_never_falls_back_to_fixture() -> None:
    failure = RateLimitedError("OpLab respondeu status 429", status=429)
    transport = ProvenanceTransport(ALL_OBSERVED, fail=failure)
    response = await chain_tool("BOVA11", "2026-11-19", config=FORGED_LIVE, clock=clock,
                                live_service=_service(transport))
    assert transport.calls == 1
    assert response == {"schema_version": "quimera-mcp-response-v1", "ok": False,
                        "degraded": False, "data": {}, "error": "OpLab respondeu status 429"}


async def test_contamination_survives_model_copy_json_and_reuse() -> None:
    priced = await _service(FixtureTransport(SYNTHETIC)).build(
        "BOVA11", date(2026, 11, 19), now=CLOCK_NOW)
    forged = priced.model_copy(update={
        "chain": priced.chain.model_copy(update={"purpose": Purpose.PRODUCTION})})
    restored = PricedChain.model_validate_json(priced.model_dump_json())
    cached = {"chave": priced}
    for candidate in (priced, forged, restored, cached["chave"], cached["chave"]):
        with pytest.raises(ProvenanceBarrierError):
            production_view(candidate, readiness=Readiness.C_PROMOTED, as_of=CLOCK_NOW)


async def test_health_reports_readiness_and_context() -> None:
    response = await _call(create_derivatives_server(TEST, clock=clock), "derivatives_health")
    assert response["status"] == "ok" and response["backend"] == SERVER_NAME
    assert response["details"] == {"readiness": "A", "provider_mode": "offline_fixture",
                                   "context": "test", "demo_tool_registered": True}


def test_system_clock_is_timezone_aware() -> None:
    assert system_clock().tzinfo is not None


def test_main_binds_loopback_with_configured_port_and_never_passes_a_live_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(self: FastMCP[Any], **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(FastMCP, "run", fake_run)
    monkeypatch.setenv("QUIMERA_DERIV_MCP_PORT", "8814")
    monkeypatch.delenv("QUIMERA_DERIV_CONTEXT", raising=False)
    monkeypatch.delenv("QUIMERA_DERIV_PROVIDER_MODE", raising=False)
    assert main() == 0
    assert captured == {"transport": "streamable-http", "host": "127.0.0.1", "port": 8814,
                        "path": "/mcp"}
