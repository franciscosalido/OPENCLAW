"""Servidor MCP ``quimera-derivatives`` (DL-PR07): superficie somente leitura.

Na Fase 1 apenas a demonstração de teste acessa a captura sintética versionada.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Never

from fastmcp import FastMCP
from loguru import logger
from starlette.middleware import Middleware as ASGIMiddleware

from backend.derivatives.config import (DerivativesConfigError, DerivativesMcpConfig,
                                        load_derivatives_mcp_config)
from backend.derivatives.mcp.http_guard import LoopbackHeaders, guard_tool_dispatch
from backend.derivatives.oplab.demo_fixture import REPO_ROOT
from backend.derivatives.oplab.errors import NotFoundError, OplabError
from backend.derivatives.oplab.routes import MarketRoute, render_route
from backend.derivatives.pricing.quote_iv import PRICE_SOURCE_NOTE, IvResultModel
from backend.derivatives.provenance import Provenance, Purpose, Readiness
from backend.derivatives.service.chain_service import ChainService, PricedChain, PricedRow
from backend.derivatives.service.demo_chain import InvalidDemoSelection, build_demo_chain
from backend.mcp.mcp_models import HealthResponse, ToolResponse
from backend.mcp.mcp_safety import validate_non_empty_text

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
    view: dict[str, object] = {
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
    if pricing.supported and contract.exercise_style.value == "AMERICAN":
        diagnostics = {key: value for key, value in pricing.assumptions.items()
                       if key.startswith("fd_")}
        if diagnostics:
            view["diagnostics"] = diagnostics
    return view

def _demo_view(priced: PricedChain, *, as_of: datetime) -> dict[str, Any]:
    """Visao compacta e serializavel da chain: precos como texto decimal, modelo em float."""
    chain, tte = priced.chain, priced.time_to_expiry
    if (chain.purpose is not Purpose.TEST or chain.stamp.purpose is not Purpose.TEST
            or chain.stamp.provenance is not Provenance.SYNTHETIC):
        raise ProvenanceBarrierError("fixture_provenance")
    return {
        "schema_version": CHAIN_SCHEMA, "status": DEMO_TEST_DATA,
        "readiness": Readiness.A_OFFLINE_VERIFIED.value,
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
                    as_of: datetime) -> Never:
    """A projeção produtiva só poderá existir após homologação própria."""
    raise ProvenanceBarrierError(LIVE_NOT_ACTIVATED)

def _inputs(symbol: str, due_date: str) -> tuple[str, date]:
    if type(symbol) is not str or type(due_date) is not str:
        raise ValueError("invalid_arguments")
    clean = validate_non_empty_text(symbol, "symbol").upper()
    render_route(MarketRoute.OPTIONS_CHAIN, symbol=clean)
    return clean, date.fromisoformat(validate_non_empty_text(due_date, "due_date"))

def _failure(code: str = "DEMO_UNAVAILABLE") -> dict[str, object]:
    """Erro constante, sem eco de entrada: o codigo e tudo o que o cliente recebe."""
    return ToolResponse(ok=False, error=code).model_dump()

async def chain_tool(
    symbol: str, due_date: str, *, config: DerivativesMcpConfig, clock: Clock,
    live_service: ChainService | None = None,
) -> dict[str, object]:
    """A Fase 1 sempre responde com prontidão A antes de acessar qualquer dado."""
    return ToolResponse(ok=True, degraded=True, data={
        "schema_version": CHAIN_SCHEMA, "status": LIVE_NOT_ACTIVATED,
        "readiness": Readiness.A_OFFLINE_VERIFIED.value, "as_of": clock().isoformat(),
        "message": "provedor ao vivo nao homologado nem promovido; sem cotacoes",
    }).model_dump()

async def demo_tool(
    symbol: str, due_date: str, *, config: DerivativesMcpConfig, root: Path,
    american_demo: bool = False, steps: int | None = None, series_registry: str | None = None,
) -> dict[str, object]:
    """Tool de demonstracao: serve a fixture configurada, sempre rotulada como teste.

    O instante de avaliacao e o do ``manifest.json`` da fixture, nao o relogio: a
    resposta e reprodutivel e nunca envelhece ate "vencer".
    """
    if (config.context != "test" or config.provider_mode != "offline_fixture"
            or config.readiness is not Readiness.A_OFFLINE_VERIFIED
            or not isinstance(config.fixture_dir, (str, Path)) or root != REPO_ROOT):
        return _failure()
    try:
        clean, expiry = _inputs(symbol, due_date)
    except (OplabError, ValueError):
        return _failure("INVALID_ARGUMENTS")
    try:
        priced, valuation = await build_demo_chain(
            clean, expiry, directory=Path(config.fixture_dir), american_demo=american_demo,
            steps=steps, series_registry=series_registry)
        data = _demo_view(priced, as_of=valuation)
    except InvalidDemoSelection:
        return _failure("INVALID_ARGUMENTS")
    except NotFoundError:
        return _failure("DEMO_SYMBOL_NOT_IN_FIXTURE")
    except (OplabError, ValueError, KeyError, OSError, ProvenanceBarrierError) as exc:
        # So o nome da classe vai para o log: sem entrada do cliente e sem payload.
        logger.warning("demonstracao de derivativos indisponivel: {}", type(exc).__name__)
        return _failure()
    return ToolResponse(ok=True, degraded=True, data=data).model_dump()

def create_derivatives_server(
    config: DerivativesMcpConfig | None = None, *, clock: Clock = system_clock,
    live_service: ChainService | None = None, root: Path | None = None,
    american_demo: bool = False, steps: int | None = None, series_registry: str | None = None,
) -> FastMCP[Any]:
    """Monta o servidor; a tool de demonstracao so existe se ``config.context == "test"``."""
    resolved = config or load_derivatives_mcp_config()
    demo_enabled = resolved.context == "test"
    server: FastMCP[Any] = FastMCP(SERVER_NAME, mask_error_details=True)
    guard_tool_dispatch(server, demo_enabled=demo_enabled)

    @server.tool
    async def derivatives_health() -> dict[str, object]:
        """Descreve o estado offline e a disponibilidade da ferramenta de demo."""
        return HealthResponse(status="ok", backend=SERVER_NAME, details={
            "readiness": Readiness.A_OFFLINE_VERIFIED.value, "provider_mode": "offline_fixture",
            "context": resolved.context, "demo_tool_registered": demo_enabled,
        }).model_dump()

    @server.tool
    async def derivatives_chain(symbol: str, due_date: str) -> dict[str, object]:
        """Responde pelo caminho padrão, sem habilitar a projeção sintética."""
        return await chain_tool(symbol, due_date, config=resolved, clock=clock,
                                live_service=live_service)

    if demo_enabled:
        @server.tool
        async def derivatives_chain_demo(symbol: str, due_date: str) -> dict[str, object]:
            """Retorna a demonstração selecionada na configuração de teste."""
            return await demo_tool(symbol, due_date, config=resolved,
                                   root=root or REPO_ROOT, american_demo=american_demo,
                                   steps=steps, series_registry=series_registry)

    return server

def main() -> int:
    """Sobe o servidor em loopback com host, porta e caminho vindos da configuracao."""
    try:
        config = load_derivatives_mcp_config()
    except DerivativesConfigError:
        # Nomes das variaveis, nunca os valores: nada do ambiente e ecoado.
        logger.error("configuracao invalida do servidor de derivativos; confira "
                     "QUIMERA_DERIV_CONTEXT, QUIMERA_DERIV_PROVIDER_MODE e "
                     "QUIMERA_DERIV_MCP_PORT")
        return 2
    server = create_derivatives_server(config)
    server.run(transport="streamable-http", host=config.host, port=config.port,
               path=config.path, middleware=[ASGIMiddleware(
                   LoopbackHeaders, port=config.port, demo_enabled=config.context == "test")],
               uvicorn_config={"access_log": False, "proxy_headers": False}, log_level="warning",
               show_banner=False)  # o banner consulta o PyPI por atualizacoes: sem rede aqui
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
