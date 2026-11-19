"""Servidor MCP ``quimera-derivatives`` (DL-PR07): superficie somente leitura.

A tool produtiva ``derivatives_chain`` responde ``LIVE_NOT_ACTIVATED`` antes do estado
C e, mesmo ativada, nunca serializa dado de teste (barreira de procedencia). A tool de
demonstracao so e registrada com ``QUIMERA_DERIV_CONTEXT=test`` no ambiente do
processo — nunca por parametro de tool. Bind fixo em ``127.0.0.1``.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from backend.derivatives.config import DerivativesMcpConfig, load_derivatives_mcp_config
from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.errors import OplabError
from backend.derivatives.oplab.routes import MarketRoute, render_route
from backend.derivatives.oplab.transport import FixtureTransport
from backend.derivatives.pricing.calendar import load_calendars
from backend.derivatives.pricing.quote_iv import PRICE_SOURCE_NOTE, IvResultModel
from backend.derivatives.provenance import Purpose, Readiness
from backend.derivatives.service.chain_service import ChainService, PricedChain, PricedRow
from backend.mcp.mcp_models import HealthResponse, ToolResponse
from backend.mcp.mcp_safety import sanitize_error, validate_non_empty_text
from config.derivatives_config_model import load_derivatives_config

SERVER_NAME = "quimera-derivatives"
CHAIN_SCHEMA = "quimera-derivatives-chain-v1"
LIVE_NOT_ACTIVATED = "LIVE_NOT_ACTIVATED"
DEMO_TEST_DATA = "DEMO_TEST_DATA"
Clock = Callable[[], datetime]

class ProvenanceBarrierError(RuntimeError):
    """Dado de teste tentou sair pela tool produtiva; a resposta e recusa, nunca cotacao."""

def system_clock() -> datetime:
    """Unico ponto do Laboratorio que le o relogio real; todo o resto recebe ``now``."""
    return datetime.now(UTC)

def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)

def _iv_side(result: IvResultModel | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {"sigma": result.sigma, "status": result.diagnostic.status.value}

def _row_view(item: PricedRow) -> dict[str, object]:
    contract, quote, pricing = item.row.contract, item.row.quote, item.pricing
    flags = item.row.quality.model_dump()
    iv = pricing.iv
    return {
        "symbol": contract.symbol, "kind": contract.kind.value,
        "exercise_style": contract.exercise_style.value, "strike": str(contract.strike),
        "bid": _text(quote.bid), "ask": _text(quote.ask), "mid": _text(quote.mid),
        "last": _text(quote.last), "supported": pricing.supported, "reason": pricing.reason,
        "model_price": _text(pricing.price), "greeks": pricing.greeks,
        "iv": None if iv is None else {
            "bid": _iv_side(iv.bid), "ask": _iv_side(iv.ask), "mid": _iv_side(iv.mid)},
        "quality_flags": sorted(name for name, value in flags.items() if value is True),
        "missing_metadata": list(item.row.quality.missing_metadata),
    }

def chain_view(priced: PricedChain, *, status: str, readiness: Readiness,
               as_of: datetime) -> dict[str, Any]:
    """Visao compacta e serializavel da chain: precos como texto decimal, modelo em float."""
    chain, tte = priced.chain, priced.time_to_expiry
    return {
        "schema_version": CHAIN_SCHEMA, "status": status, "readiness": readiness.value,
        "purpose": priced.purpose.value, "provenance": chain.stamp.provenance.value,
        "as_of": as_of.isoformat(), "underlying": chain.underlying,
        "expiry": chain.expiry.isoformat(), "valuation_date": priced.valuation_date.isoformat(),
        "market_status": priced.market_status,
        "spot": None if chain.spot is None else {
            "price": str(chain.spot.price), "source": chain.spot.source.value},
        "rate": None if chain.rate is None else {
            "uid": chain.rate.uid, "value_pct_aa": str(chain.rate.value_pct_aa)},
        "time_to_expiry": None if tte is None else {
            "business_days": tte.business_days, "year_fraction": tte.year_fraction,
            "convention": tte.convention, "basis": tte.basis},
        "unpriceable_reason": priced.unpriceable_reason,
        "price_source_note": PRICE_SOURCE_NOTE,
        "model_assumptions": dict(chain.model_assumptions),
        "row_count": len(priced.rows), "rows": [_row_view(item) for item in priced.rows],
    }

def production_view(priced: PricedChain, *, readiness: Readiness,
                    as_of: datetime) -> dict[str, Any]:
    """Barreira deterministica: so chain com proposito efetivo de producao e serializada.

    Raises:
        ProvenanceBarrierError: qualquer leitura de teste na captura (worst-of).
    """
    if priced.purpose is not Purpose.PRODUCTION:
        raise ProvenanceBarrierError("dado de teste bloqueado na tool produtiva")
    return chain_view(priced, status="OK", readiness=readiness, as_of=as_of)

def _inputs(symbol: str, due_date: str) -> tuple[str, date]:
    clean = validate_non_empty_text(symbol, "symbol").upper()
    render_route(MarketRoute.OPTIONS_CHAIN, symbol=clean)
    return clean, date.fromisoformat(validate_non_empty_text(due_date, "due_date"))

def _failure(exc: BaseException) -> dict[str, object]:
    return ToolResponse(ok=False, error=sanitize_error(exc)).model_dump()

async def chain_tool(
    symbol: str, due_date: str, *, config: DerivativesMcpConfig, clock: Clock,
    live_service: ChainService | None = None,
) -> dict[str, object]:
    """Tool produtiva: ``LIVE_NOT_ACTIVATED`` antes do estado C; nunca usa fixture."""
    try:
        clean, expiry = _inputs(symbol, due_date)
    except (OplabError, ValueError) as exc:
        return _failure(exc)
    now = clock()
    activated = (config.provider_mode == "live_homologated"
                 and config.readiness is Readiness.C_PROMOTED and live_service is not None)
    if not activated or live_service is None:
        return ToolResponse(ok=True, degraded=True, data={
            "schema_version": CHAIN_SCHEMA, "status": LIVE_NOT_ACTIVATED,
            "readiness": config.readiness.value, "as_of": now.isoformat(),
            "message": "provedor ao vivo nao homologado nem promovido; sem cotacoes",
        }).model_dump()
    try:
        priced = await live_service.build(clean, expiry, now=now)
        data = production_view(priced, readiness=config.readiness, as_of=now)
    except (OplabError, ValueError, ProvenanceBarrierError) as exc:
        return _failure(exc)
    return ToolResponse(ok=True, data=data).model_dump()

async def demo_tool(
    symbol: str, due_date: str, *, config: DerivativesMcpConfig, root: Path,
) -> dict[str, object]:
    """Tool de demonstracao: serve a fixture configurada, sempre rotulada como teste.

    O instante de avaliacao e o do ``manifest.json`` da fixture, nao o relogio: a
    resposta e reprodutivel e nunca envelhece ate "vencer".
    """
    if config.context != "test" or config.fixture_dir is None:
        return _failure(ValueError("demonstracao exige contexto test e diretorio de fixture"))
    try:
        clean, expiry = _inputs(symbol, due_date)
        directory = Path(config.fixture_dir)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        valuation = datetime.fromisoformat(manifest["valuation"])
        cfg = load_derivatives_config()
        client = OplabMarketClient(FixtureTransport(directory), stamp_source="fixture:")
        service = ChainService(client, cfg=cfg,
                               calendars=load_calendars(cfg.conventions, root=root))
        priced = await service.build(clean, expiry, now=valuation)
    except (OplabError, ValueError, KeyError, OSError) as exc:
        return _failure(exc)
    if priced.purpose is not Purpose.TEST:
        return _failure(ProvenanceBarrierError("demonstracao so serve dado de teste"))
    data = chain_view(priced, status=DEMO_TEST_DATA, readiness=config.readiness,
                      as_of=valuation)
    return ToolResponse(ok=True, degraded=True, data=data).model_dump()

def create_derivatives_server(
    config: DerivativesMcpConfig | None = None, *, clock: Clock = system_clock,
    live_service: ChainService | None = None, root: Path | None = None,
) -> FastMCP[Any]:
    """Monta o servidor; a tool de demonstracao so existe se ``config.context == "test"``."""
    resolved = config or load_derivatives_mcp_config()
    server: FastMCP[Any] = FastMCP(SERVER_NAME)
    demo_enabled = resolved.context == "test"

    @server.tool
    async def derivatives_health() -> dict[str, object]:
        return HealthResponse(status="ok", backend=SERVER_NAME, details={
            "readiness": resolved.readiness.value, "provider_mode": resolved.provider_mode,
            "context": resolved.context, "demo_tool_registered": demo_enabled,
        }).model_dump()

    @server.tool
    async def derivatives_chain(symbol: str, due_date: str) -> dict[str, object]:
        return await chain_tool(symbol, due_date, config=resolved, clock=clock,
                                live_service=live_service)

    if demo_enabled:
        @server.tool
        async def derivatives_chain_demo(symbol: str, due_date: str) -> dict[str, object]:
            return await demo_tool(symbol, due_date, config=resolved,
                                   root=root or Path.cwd())

    return server

def main() -> int:
    """Sobe o servidor em loopback com host, porta e caminho vindos da configuracao."""
    config = load_derivatives_mcp_config()
    server = create_derivatives_server(config)
    server.run(transport="streamable-http", host=config.host, port=config.port,
               path=config.path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
