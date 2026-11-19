"""Servico de chain (DL-PR06): uma captura -> normalizacao -> qualidade -> IV e BSM.

Unico modulo que compoe fornecedor, dominio e precificacao. Os tres passos sao
publicos (``acquire``, ``normalize``, ``price``) para que o protocolo de latencia os
meca em separado; nao ha relogio interno, cache nem retry aqui.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from backend.derivatives.adapters.normalize import normalize_chain
from backend.derivatives.domain.models import Chain, OptionRow
from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.vendor_models import (VendorInterestRate, VendorMarketStatus,
    VendorOption, VendorStock)
from backend.derivatives.pricing.calendar import (CalendarCoverageError, CalendarId,
    TradingCalendar)
from backend.derivatives.pricing.contract_pricing import (PricingOutcome,
    price_contract_from_quote)
from backend.derivatives.pricing.conventions import (TimeToExpiry, continuous_rate,
    model_assumptions, time_to_expiry)
from backend.derivatives.provenance import ProvenanceStamp, Purpose, inherit_purpose, purpose_of
from config.derivatives_config_model import DerivativesConfig

B3_TIMEZONE = ZoneInfo("America/Sao_Paulo")
CALLS_PER_CAPTURE = 4
SERVICE_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)

@dataclass(frozen=True, slots=True)
class Capture:
    """Uma aquisicao: quatro leituras do mesmo instante e o carimbo worst-of delas."""
    symbol: str
    options: tuple[VendorOption, ...]
    stock: VendorStock
    rates: tuple[VendorInterestRate, ...]
    status: VendorMarketStatus
    stamp: ProvenanceStamp

class PricedRow(BaseModel):
    """Linha da chain com o resultado da ponte de precificacao (ou a recusa explicada)."""
    model_config = SERVICE_MODEL_CONFIG
    row: OptionRow
    pricing: PricingOutcome

class PricedChain(BaseModel):
    """Chain precificada. ``unpriceable_reason`` explica quando nenhuma linha tem numeros."""
    model_config = SERVICE_MODEL_CONFIG
    schema_version: Literal["quimera-derivatives-priced-chain-v1"] = (
        "quimera-derivatives-priced-chain-v1")
    chain: Chain
    rows: tuple[PricedRow, ...]
    market_status: str
    valuation_date: date
    time_to_expiry: TimeToExpiry | None
    unpriceable_reason: str | None

    @property
    def purpose(self) -> Purpose:
        """Proposito efetivo, worst-of entre campo, carimbo e procedencia.

        A troca isolada de propósito não promove a chain. Este cálculo não autentica
        um carimbo substituído e não autoriza uma projeção produtiva.
        """
        stamp = self.chain.stamp
        return inherit_purpose(self.chain.purpose, stamp.purpose, purpose_of(stamp.provenance))

class ChainService:
    """Compoe cliente, normalizador e precificador sobre uma unica captura."""

    def __init__(
        self, client: OplabMarketClient, *, cfg: DerivativesConfig,
        calendars: Mapping[CalendarId, TradingCalendar],
    ) -> None:
        """``calendars`` vem de ``load_calendars`` (carregado uma vez por processo)."""
        self._client = client
        self._cfg = cfg
        trading = cfg.conventions.day_count_calendar == "trading"
        self._calendar = calendars[
            CalendarId.B3_LISTED_TRADING if trading else CalendarId.BR_ANBIMA_BUSINESS]

    async def acquire(self, symbol: str, *, now: datetime) -> Capture:
        """Faz exatamente quatro leituras (chain, ativo, taxas, status), em ordem fixa.

        O carimbo da captura herda worst-of: uma unica leitura de teste rebaixa tudo.
        """
        options, options_stamp = await self._client.options_chain(symbol, now=now)
        stock, stock_stamp = await self._client.stock(symbol, now=now)
        rates, rates_stamp = await self._client.interest_rates(now=now)
        status, status_stamp = await self._client.market_status(now=now)
        stamps = (options_stamp, stock_stamp, rates_stamp, status_stamp)
        stamp = ProvenanceStamp(
            provenance=options_stamp.provenance,
            purpose=inherit_purpose(*(item.purpose for item in stamps)),
            source=options_stamp.source, captured_at=options_stamp.captured_at,
            note=f"captura unica de {len(stamps)} leituras; proposito worst-of")
        return Capture(symbol, options, stock, rates, status, stamp)

    def normalize(self, capture: Capture, expiry: date, *, now: datetime) -> Chain:
        """Normaliza o vencimento pedido e carrega as hipoteses do modelo na chain."""
        chain = normalize_chain(
            options=capture.options, stock=capture.stock, rates=capture.rates,
            underlying=capture.symbol, expiry=expiry, stamp=capture.stamp, now=now,
            quality_cfg=self._cfg.quality)
        assumptions = model_assumptions(self._cfg.conventions, self._calendar)
        return chain.model_copy(update={"model_assumptions": assumptions})

    def _time(self, chain: Chain, valuation: date) -> tuple[TimeToExpiry | None, str | None]:
        conventions = self._cfg.conventions
        if conventions.day_count != "business_252":
            return None, f"unsupported_day_count:{conventions.day_count}"
        if chain.spot is None:
            return None, "missing_spot"
        if chain.rate is None:
            return None, "missing_rate"
        try:
            return time_to_expiry(self._calendar, valuation_date=valuation,
                                  expiry=chain.expiry, cfg=conventions), None
        except CalendarCoverageError:
            return None, "calendar_coverage"
        except ValueError:
            return None, "expiry_before_valuation"

    def price(self, chain: Chain, *, market_status: str, now: datetime) -> PricedChain:
        """IV de bid/ask/mid e BSM (sigma do mid) por linha; recusa sempre explicada.

        A data de avaliacao e ``now`` no fuso da B3. Sem spot, taxa, cobertura de
        calendario ou prazo valido, toda linha recebe ``chain_unpriceable:<motivo>``.
        """
        valuation = now.astimezone(B3_TIMEZONE).date()
        tte, reason = self._time(chain, valuation)
        rows: list[PricedRow] = []
        for row in chain.rows:
            if tte is None or chain.spot is None or chain.rate is None:
                outcome = PricingOutcome(
                    supported=False, reason=f"chain_unpriceable:{reason}", model=None,
                    price=None, greeks=None, regime=None,
                    inputs_echo={"symbol": row.contract.symbol},
                    assumptions=dict(chain.model_assumptions))
            else:
                outcome = price_contract_from_quote(
                    row.contract, row.quote, spot=chain.spot.price,
                    rate_cont=continuous_rate(
                        chain.rate.value_pct_aa,
                        compounding=self._cfg.conventions.rate_compounding),
                    tte=tte, cfg_conv=self._cfg.conventions, cfg_iv=self._cfg.iv,
                    assumptions=chain.model_assumptions)
            rows.append(PricedRow(row=row, pricing=outcome))
        return PricedChain(chain=chain, rows=tuple(rows), market_status=market_status,
                           valuation_date=valuation, time_to_expiry=tte,
                           unpriceable_reason=reason)

    async def build(self, symbol: str, expiry: date, *, now: datetime) -> PricedChain:
        """Uma captura (quatro leituras) alimenta todos os calculos da chain pedida."""
        capture = await self.acquire(symbol, now=now)
        chain = self.normalize(capture, expiry, now=now)
        return self.price(chain, market_status=capture.status.market_status, now=now)
