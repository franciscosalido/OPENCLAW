"""Ponte dominio -> modelo (DL-PR03/04): so europeias recebem BSM; recusa explicita.

``price_contract`` segue recebendo ``sigma`` resolvido pelo chamador; o DL-PR04
acrescenta ``price_contract_from_quote``, que resolve sigma pela IV da cotacao na
fonte pedida e recusa com ``iv_unavailable:<motivo>`` quando nao ha IV utilizavel.
Americanas nunca recebem BSM nem IV (ADR-0023, decisao 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.derivatives.domain.models import ExerciseStyle, OptionContract, Quote
from backend.derivatives.pricing.bsm import BsmInputs, PricingModel, price, unsupported
from backend.derivatives.pricing.conventions import TimeToExpiry
from backend.derivatives.pricing.implied_vol import STATUSES_WITH_SIGMA
from backend.derivatives.pricing.quote_iv import IvResultModel, QuoteIv, iv_for_quote
from config.derivatives_config_model import Conventions, Iv


class PricingOutcome(BaseModel):
    """Resultado da ponte: ou preco BSM completo, ou recusa com motivo e campos nulos.
    ``iv`` (diagnosticos bid/ask/mid) e ``sigma_source`` (origem do sigma usado) sao
    opcionais do DL-PR04 e nao mudam chamadas do PR03."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supported: bool
    reason: str | None
    model: str | None
    price: Decimal | None
    greeks: dict[str, float] | None
    regime: str | None
    inputs_echo: dict[str, float | str]
    assumptions: dict[str, str | float | bool]
    iv: QuoteIv | None = None
    sigma_source: Literal["mid", "bid", "ask", "given"] | None = None


def _inputs_echo(
    contract: OptionContract,
    spot: Decimal,
    rate_cont: float,
    sigma: float | str,
    tte: TimeToExpiry,
    cfg: Conventions,
) -> dict[str, float | str]:
    """Echo auditavel das entradas; ``sigma`` e ``"unresolved"`` quando nao ha IV."""
    return {
        "symbol": contract.symbol,
        "kind": contract.kind.value,
        "exercise_style": contract.exercise_style.value,
        "spot": float(spot),
        "strike": float(contract.strike),
        "time_years": tte.year_fraction,
        "rate_cont": rate_cont,
        "sigma": sigma,
        "dividend_yield": cfg.dividend_yield,
        "theta_basis": float(cfg.year_basis),
    }


def price_contract(
    contract: OptionContract,
    *,
    spot: Decimal,
    rate_cont: float,
    sigma: float,
    tte: TimeToExpiry,
    cfg: Conventions,
    assumptions: Mapping[str, str | float | bool],
) -> PricingOutcome:
    """Aplica BSM a um contrato europeu; qualquer outro estilo e recusado sem numeros."""
    echo = _inputs_echo(contract, spot, rate_cont, sigma, tte, cfg)
    if contract.exercise_style is not ExerciseStyle.EUROPEAN:
        return PricingOutcome(
            supported=False, reason=unsupported(contract.exercise_style), model=None,
            price=None, greeks=None, regime=None, inputs_echo=echo,
            assumptions=dict(assumptions),
        )
    result = price(
        BsmInputs(
            kind=contract.kind, spot=float(spot), strike=float(contract.strike),
            time_years=tte.year_fraction, rate_cont=rate_cont, sigma=sigma,
            dividend_yield=cfg.dividend_yield,
        ),
        theta_basis=cfg.year_basis,
    )
    greeks: dict[str, float] = {
        "delta": result.greeks.delta,
        "gamma": result.greeks.gamma,
        "vega_per_pct_point": result.greeks.vega_per_pct_point,
        "theta_per_day": result.greeks.theta_per_day,
        "rho_per_pct_point": result.greeks.rho_per_pct_point,
        "theta_basis": float(result.greeks.theta_basis),
    }
    merged: dict[str, str | float | bool] = {
        **assumptions, "pricing_model": PricingModel.BSM_EUROPEAN.value,
    }
    return PricingOutcome(
        supported=True, reason=None, model=PricingModel.BSM_EUROPEAN.value,
        price=Decimal(str(result.price)), greeks=greeks, regime=result.regime,
        inputs_echo=echo, assumptions=merged,
    )


def _refused_from_quote(
    contract: OptionContract,
    reason: str,
    quote_iv: QuoteIv | None,
    spot: Decimal,
    rate_cont: float,
    tte: TimeToExpiry,
    cfg: Conventions,
    assumptions: Mapping[str, str | float | bool],
) -> PricingOutcome:
    """Recusa explicada: numericos ``None``; diagnosticos de IV quando existirem."""
    echo = _inputs_echo(contract, spot, rate_cont, "unresolved", tte, cfg)
    return PricingOutcome(
        supported=False, reason=reason, model=None, price=None, greeks=None,
        regime=None, inputs_echo=echo, assumptions=dict(assumptions), iv=quote_iv,
        sigma_source=None,
    )


def price_contract_from_quote(
    contract: OptionContract,
    quote: Quote,
    *,
    spot: Decimal,
    rate_cont: float,
    tte: TimeToExpiry,
    cfg_conv: Conventions,
    cfg_iv: Iv,
    assumptions: Mapping[str, str | float | bool],
    sigma_source: Literal["mid", "bid", "ask"] = "mid",
) -> PricingOutcome:
    """Resolve sigma pela IV da cotacao na fonte pedida e aplica ``price_contract``.

    Americana/estilo desconhecido recusa ANTES de qualquer IV (``iv=None``). Fonte
    pedida ausente na cotacao vira ``iv_unavailable:missing_quote``; fonte com
    status fora de ``{OK, LOW_VEGA}`` vira ``iv_unavailable:<status>`` — em ambos
    os casos ``iv`` carrega os diagnosticos completos de bid/ask/mid.
    """
    if contract.exercise_style is not ExerciseStyle.EUROPEAN:
        return _refused_from_quote(contract, unsupported(contract.exercise_style),
                                   None, spot, rate_cont, tte, cfg_conv, assumptions)
    quote_iv = iv_for_quote(quote, contract, spot=spot, rate_cont=rate_cont, tte=tte,
                            cfg=cfg_iv, dividend_yield=cfg_conv.dividend_yield)
    sides: dict[str, IvResultModel | None] = {
        "mid": quote_iv.mid, "bid": quote_iv.bid, "ask": quote_iv.ask,
    }
    chosen = sides[sigma_source]
    if chosen is None:
        return _refused_from_quote(contract, "iv_unavailable:missing_quote", quote_iv,
                                   spot, rate_cont, tte, cfg_conv, assumptions)
    if chosen.diagnostic.status not in STATUSES_WITH_SIGMA or chosen.sigma is None:
        reason = f"iv_unavailable:{chosen.diagnostic.status.value}"
        return _refused_from_quote(contract, reason, quote_iv, spot, rate_cont, tte,
                                   cfg_conv, assumptions)
    outcome = price_contract(contract, spot=spot, rate_cont=rate_cont,
                             sigma=chosen.sigma, tte=tte, cfg=cfg_conv,
                             assumptions=assumptions)
    return outcome.model_copy(update={"iv": quote_iv, "sigma_source": sigma_source})
