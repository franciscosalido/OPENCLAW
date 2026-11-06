"""Normalizacao fornecedor -> dominio, funcoes puras com relogio injetado (DL-PR01).

Mora em ``backend.derivatives.adapters`` para o pacote de dominio nunca importar
``backend.derivatives.oplab`` (fronteira garantida por teste de arquitetura).
Zero-vs-ausente decide-se aqui: preco zero sem volume e ausencia, nunca cotacao.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from loguru import logger
from pydantic import BaseModel

from backend.derivatives.domain.models import (Chain, ExerciseStyle, OptionContract, OptionKind,
    OptionRow, Quote, RateObservation, SpotObservation, SpotSource)
from backend.derivatives.domain.quality import assess_quality
from backend.derivatives.oplab.vendor_models import (VendorInterestRate, VendorOption,
    VendorStock, unknown_fields)
from backend.derivatives.provenance import ProvenanceStamp, inherit_purpose
from config.derivatives_config_model import Quality

class NormalizationError(ValueError):
    """Entrada do fornecedor sem o minimo necessario para o dominio."""

def epoch_ms_to_datetime(value: int | None) -> datetime | None:
    """Epoch em milissegundos para UTC aware; ``None`` e ``0`` viram ``None``."""
    if not value:
        return None
    seconds, ms = divmod(value, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(milliseconds=ms)

def money(value: float | None) -> Decimal | None:
    """Preco float para ``Decimal`` exato via ``str``; zero e preservado."""
    return None if value is None else Decimal(str(value))

def _side(price: float | None, size: int | None) -> Decimal | None:
    return None if price is None or (price == 0 and (size or 0) == 0) else money(price)

def quote_from_vendor(opt: VendorOption, *, received_at: datetime) -> Quote:
    """Normaliza a cotacao: lado zerado sem volume e ausente; tempos via epoch ms."""
    no_last = opt.close is None or (
        opt.close == 0 and (opt.volume or 0) == 0 and (opt.trades or 0) == 0)
    return Quote(
        bid=_side(opt.bid, opt.bid_volume), ask=_side(opt.ask, opt.ask_volume),
        last=None if no_last else money(opt.close), bid_size=opt.bid_volume,
        ask_size=opt.ask_volume, volume=opt.volume, trades=opt.trades,
        last_trade_at=epoch_ms_to_datetime(opt.last_trade_at),
        source_time=epoch_ms_to_datetime(opt.time), received_at=received_at)

def contract_from_vendor(
    opt: VendorOption, *, underlying: str, quotation_form: int | None
) -> OptionContract:
    """Identidade do contrato; ``maturity_type`` ausente vira UNKNOWN; strike ausente e erro."""
    strike = money(opt.strike)
    if strike is None:
        raise NormalizationError(f"opcao {opt.symbol}: strike ausente")
    style = ExerciseStyle.UNKNOWN if opt.maturity_type is None else ExerciseStyle(opt.maturity_type)
    return OptionContract(
        symbol=opt.symbol, underlying=underlying, kind=OptionKind(opt.category),
        exercise_style=style, strike=strike, expiry=opt.due_date,
        contract_size=opt.contract_size, quotation_form=quotation_form, isin=opt.isin)

def spot_from_vendor(
    stock: VendorStock | None, options: Sequence[VendorOption]
) -> SpotObservation | None:
    """Spot do endpoint de ativo; sem ele, ``spot_price`` da opcao com negocio mais recente."""
    price = None if stock is None else money(stock.close)
    if stock is not None and price is not None:
        return SpotObservation(price=price, source=SpotSource.STOCK_ENDPOINT,
            observed_at=epoch_ms_to_datetime(stock.time))
    candidates = [o for o in options if o.spot_price is not None and (o.last_trade_at or 0) > 0]
    if not candidates:
        return None
    best = max(candidates, key=lambda o: o.last_trade_at or 0)
    price = money(best.spot_price)
    return None if price is None else SpotObservation(price=price,
        source=SpotSource.OPTION_LAST_TRADE, observed_at=epoch_ms_to_datetime(best.last_trade_at))

def rate_from_vendor(
    rates: Sequence[VendorInterestRate], *, preferred_uid: str = "SELIC"
) -> RateObservation | None:
    """Taxa preferida (fallback: primeira); capitalizacao exponencial 252 e hipotese ADR-0023."""
    chosen = next((r for r in rates if r.uid == preferred_uid), rates[0] if rates else None)
    value = None if chosen is None else money(chosen.value)
    if chosen is None or value is None:
        return None
    return RateObservation(uid=chosen.uid, value_pct_aa=value, observed_at=chosen.updated_at,
        compounding_assumed=True)

def _warn_unknown_once(models: Iterable[BaseModel], seen: set[str]) -> None:
    for model in models:
        for field in unknown_fields(model):
            if field not in seen:
                seen.add(field)
                logger.warning("campo desconhecido do fornecedor OpLab ignorado: {}", field)

def normalize_chain(
    *, options: Sequence[VendorOption], stock: VendorStock | None,
    rates: Sequence[VendorInterestRate], underlying: str, expiry: date,
    stamp: ProvenanceStamp, now: datetime, quality_cfg: Quality,
) -> Chain:
    """Chain do vencimento pedido; proposito herdado worst-of; ``now`` naive e erro."""
    if now.tzinfo is None:
        raise NormalizationError("now deve ser datetime tz-aware")
    seen: set[str] = set()
    _warn_unknown_once(options, seen)
    _warn_unknown_once([] if stock is None else [stock], seen)
    _warn_unknown_once(rates, seen)
    selected = [opt for opt in options if opt.due_date == expiry]
    spot = spot_from_vendor(stock, selected)
    quotation_form = None if stock is None else stock.quotation_form
    rows: list[OptionRow] = []
    for opt in selected:
        contract = contract_from_vendor(opt, underlying=underlying, quotation_form=quotation_form)
        quote = quote_from_vendor(opt, received_at=now)
        flags = assess_quality(quote=quote, contract=contract, spot=spot, now=now, cfg=quality_cfg)
        rows.append(OptionRow(contract=contract, quote=quote, quality=flags))
    rows.sort(key=lambda row: (row.contract.kind.value, row.contract.strike))
    return Chain(
        underlying=underlying, expiry=expiry, spot=spot, rate=rate_from_vendor(rates),
        rows=tuple(rows), stamp=stamp, purpose=inherit_purpose(stamp.purpose),
        acquired_at=now, model_assumptions={})
