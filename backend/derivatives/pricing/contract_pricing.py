"""Ponte dominio -> modelo (DL-PR03): so europeias recebem BSM; a recusa e explicita.

Nao le cotacoes nem escolhe sigma (IV bid/ask/mid e assunto do DL-PR04); o chamador
injeta spot, taxa continua e volatilidade ja resolvidos. Americanas nunca recebem BSM
"por aproximacao" (ADR-0023, decisao 4): a resposta e ``supported=False`` com motivo.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.derivatives.domain.models import ExerciseStyle, OptionContract
from backend.derivatives.pricing.bsm import BsmInputs, PricingModel, price, unsupported
from backend.derivatives.pricing.conventions import TimeToExpiry
from config.derivatives_config_model import Conventions


class PricingOutcome(BaseModel):
    """Resultado da ponte: ou preco BSM completo, ou recusa com motivo e campos nulos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supported: bool
    reason: str | None
    model: str | None
    price: Decimal | None
    greeks: dict[str, float] | None
    regime: str | None
    inputs_echo: dict[str, float | str]
    assumptions: dict[str, str | float | bool]


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
    echo: dict[str, float | str] = {
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
