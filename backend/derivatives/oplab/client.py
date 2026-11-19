"""Cliente Market da OpLab (DL-PR05): transporte -> modelos do fornecedor + carimbo de
procedencia. O JSON bruto nunca sai deste pacote; nao ha cache nem retry aqui."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError

from backend.derivatives.oplab.routes import MarketRoute
from backend.derivatives.oplab.transport import Transport, VendorResponse
from backend.derivatives.oplab.vendor_models import (VendorInterestRate, VendorMarketStatus,
    VendorOption, VendorPayloadError, VendorStock, parse_vendor_interest_rates,
    parse_vendor_market_status, parse_vendor_options, parse_vendor_stock)
from backend.derivatives.provenance import ProvenanceStamp, purpose_of

class OplabMarketClient:
    """Quatro leituras de mercado tipadas; a procedencia vem do transporte."""

    def __init__(self, transport: Transport, *, stamp_source: str) -> None:
        """``stamp_source`` prefixa a rota em ``ProvenanceStamp.source``."""
        self._transport = transport
        self._stamp_source = stamp_source

    async def _read[T](
        self, route: MarketRoute, parse: Callable[[object], T], now: datetime, **params: str,
    ) -> tuple[T, ProvenanceStamp]:
        response: VendorResponse = await self._transport.get(route, params=params, now=now)
        try:
            parsed = parse(response.json)
        except ValidationError as exc:
            # ``from None``: o erro do pydantic carrega os valores do payload bruto.
            raise VendorPayloadError(
                f"{response.route}: {exc.error_count()} erro(s) de validacao") from None
        stamp = ProvenanceStamp(
            provenance=response.provenance, purpose=purpose_of(response.provenance),
            source=f"{self._stamp_source}{response.route}", captured_at=response.received_at)
        return parsed, stamp

    async def options_chain(
        self, symbol: str, *, now: datetime,
    ) -> tuple[tuple[VendorOption, ...], ProvenanceStamp]:
        """Opcoes do subjacente (todas as series devolvidas pelo fornecedor)."""
        return await self._read(MarketRoute.OPTIONS_CHAIN, parse_vendor_options, now,
                                symbol=symbol)

    async def stock(self, symbol: str, *, now: datetime) -> tuple[VendorStock, ProvenanceStamp]:
        """Cotacao e metadados do ativo-objeto (``quotation_form``, ``contract_size``)."""
        return await self._read(MarketRoute.STOCK, parse_vendor_stock, now, symbol=symbol)

    async def interest_rates(
        self, *, now: datetime,
    ) -> tuple[tuple[VendorInterestRate, ...], ProvenanceStamp]:
        """Taxas de juros publicadas pelo fornecedor (% a.a.)."""
        return await self._read(MarketRoute.INTEREST_RATES, parse_vendor_interest_rates, now)

    async def market_status(
        self, *, now: datetime,
    ) -> tuple[VendorMarketStatus, ProvenanceStamp]:
        """Estado do mercado e horario do servidor do fornecedor."""
        return await self._read(MarketRoute.MARKET_STATUS, parse_vendor_market_status, now)
