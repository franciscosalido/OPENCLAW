"""Volatilidade implicita por bissecao protegida (DL-PR04): inversao preco -> sigma.

Ausencia de solucao e sempre ``sigma=None`` com diagnostico completo; ``sigma == 0.0``
jamais marca ausencia. A funcao de preco e exclusivamente ``bsm.price`` (ADR-0023).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from backend.derivatives.domain.models import OptionKind
from backend.derivatives.pricing.bsm import BsmInputs, BsmResult, PricingDomainError, price

if TYPE_CHECKING:
    from config.derivatives_config_model import Iv


class IvStatus(StrEnum):
    """Desfecho da inversao; so ``OK`` e ``LOW_VEGA`` carregam ``sigma``."""

    OK = "ok"
    BELOW_INTRINSIC = "below_intrinsic"
    ABOVE_UPPER_BOUND = "above_upper_bound"
    NO_CONVERGENCE = "no_convergence"
    LOW_VEGA = "low_vega"
    NOT_APPLICABLE = "not_applicable"
    DOMAIN_ERROR = "domain_error"


STATUSES_WITH_SIGMA = frozenset({IvStatus.OK, IvStatus.LOW_VEGA})


@dataclass(frozen=True, slots=True)
class IvDiagnostic:
    """Diagnostico auditavel: bracket final, residuos assinados, vega e expansoes."""

    status: IvStatus
    iterations: int
    bracket_lo: float | None
    bracket_hi: float | None
    residual_price: float | None
    residual_vol: float | None
    vega_at_solution: float | None
    expansions: int
    message: str


@dataclass(frozen=True, slots=True)
class IvResult:
    """Resultado da inversao. Invariante: ``sigma is None`` <=> status sem solucao."""

    sigma: float | None
    diagnostic: IvDiagnostic

    def __post_init__(self) -> None:
        """Garante o invariante sigma/status; zero nunca e marcador de ausencia."""
        expects_sigma = self.diagnostic.status in STATUSES_WITH_SIGMA
        if (self.sigma is not None) is not expects_sigma:
            raise ValueError(
                f"sigma e status inconsistentes: {self.sigma!r} / {self.diagnostic.status}"
            )
        if self.sigma is not None and self.sigma <= 0.0:
            raise ValueError("sigma de solucao deve ser estritamente positivo")


def price_bounds(
    kind: OptionKind,
    spot: float,
    strike: float,
    time_years: float,
    rate_cont: float,
    dividend_yield: float,
) -> tuple[float, float]:
    """Limites de nao-arbitragem: call ``[max(S e^{-qT} - K e^{-rT}, 0), S e^{-qT}]``;
    put simetrica com teto ``K e^{-rT}``. Alvo fora deles nao tem sigma."""
    forward_leg = spot * math.exp(-dividend_yield * time_years)
    strike_leg = strike * math.exp(-rate_cont * time_years)
    if kind is OptionKind.CALL:
        return max(forward_leg - strike_leg, 0.0), forward_leg
    return max(strike_leg - forward_leg, 0.0), strike_leg


def _no_solution(
    status: IvStatus,
    message: str,
    *,
    iterations: int = 0,
    bracket: tuple[float, float] | None = None,
    residuals: tuple[float, float] | None = None,
    expansions: int = 0,
) -> IvResult:
    """Resultado sem ``sigma``; o motivo vai inteiro para o diagnostico."""
    lo, hi = bracket if bracket is not None else (None, None)
    residual_price, residual_vol = residuals if residuals is not None else (None, None)
    diagnostic = IvDiagnostic(status, iterations, lo, hi, residual_price, residual_vol,
                              None, expansions, message)
    return IvResult(None, diagnostic)


def implied_vol(
    target_price: float,
    *,
    kind: OptionKind,
    spot: float,
    strike: float,
    time_years: float,
    rate_cont: float,
    dividend_yield: float,
    cfg: Iv,
) -> IvResult:
    """Inverte o preco BSM em sigma por bissecao protegida, com diagnostico completo.

    Entrada invalida vira ``DOMAIN_ERROR`` (nenhuma excecao escapa); ``T == 0`` vira
    ``NOT_APPLICABLE``. Exige mudanca de sinal estrita no bracket (expansao dobrando
    ``hi`` ate ``bracket_hi_max``, contada) e para somente com a tolerancia dupla:
    ``|preco(sigma) - alvo| <= tol_price`` E ``hi - lo <= tol_vol``. Estourar
    ``max_iterations`` devolve ``sigma=None`` — nunca o meio do bracket.
    Deterministico: mesma entrada, mesmos bits e mesmas ``iterations``.
    """
    if not math.isfinite(target_price) or target_price < 0.0:
        return _no_solution(IvStatus.DOMAIN_ERROR,
                            "preco alvo deve ser finito e nao negativo")
    try:
        BsmInputs(kind=kind, spot=spot, strike=strike, time_years=time_years,
                  rate_cont=rate_cont, sigma=cfg.bracket_lo,
                  dividend_yield=dividend_yield)
    except PricingDomainError as exc:
        return _no_solution(IvStatus.DOMAIN_ERROR, str(exc))
    if time_years == 0.0:
        return _no_solution(IvStatus.NOT_APPLICABLE,
                            "T == 0: preco de vencimento nao determina sigma")

    def evaluate(sigma: float) -> BsmResult:
        inputs = BsmInputs(kind=kind, spot=spot, strike=strike, time_years=time_years,
                           rate_cont=rate_cont, sigma=sigma,
                           dividend_yield=dividend_yield)
        return price(inputs, theta_basis=252)

    lower, upper = price_bounds(kind, spot, strike, time_years, rate_cont,
                                dividend_yield)
    tol_price = cfg.tol_price_rel * max(1.0, target_price)
    if target_price < lower - tol_price:
        return _no_solution(
            IvStatus.BELOW_INTRINSIC,
            f"alvo {target_price!r} abaixo do intrinseco descontado {lower!r}")
    if target_price > upper + tol_price:
        return _no_solution(
            IvStatus.ABOVE_UPPER_BOUND,
            f"alvo {target_price!r} acima do teto sem arbitragem {upper!r}")
    lo, hi = cfg.bracket_lo, cfg.bracket_hi
    f_lo = evaluate(lo).price - target_price
    f_hi = evaluate(hi).price - target_price
    expansions = 0
    while f_hi < 0.0 and hi < cfg.bracket_hi_max:
        hi = min(2.0 * hi, cfg.bracket_hi_max)
        expansions += 1
        f_hi = evaluate(hi).price - target_price
    if f_hi < 0.0:
        return _no_solution(
            IvStatus.NO_CONVERGENCE,
            "sem mudanca de sinal: alvo acima do preco em bracket_hi_max",
            bracket=(lo, hi), expansions=expansions)
    if f_lo > 0.0:
        return _no_solution(
            IvStatus.NO_CONVERGENCE,
            "sem mudanca de sinal: raiz abaixo de bracket_lo (alvo no intrinseco "
            "ou abaixo da resolucao do modelo)",
            bracket=(lo, hi), expansions=expansions)
    iterations = 0
    mid, f_mid = lo, f_lo
    at_solution: BsmResult | None = None
    while iterations < cfg.max_iterations:
        mid = 0.5 * (lo + hi)
        at_mid = evaluate(mid)
        f_mid = at_mid.price - target_price
        iterations += 1
        if f_mid > 0.0:
            hi = mid
        else:
            lo = mid
        if abs(f_mid) <= tol_price and hi - lo <= cfg.tol_vol:
            at_solution = at_mid
            break
    if at_solution is None:
        return _no_solution(
            IvStatus.NO_CONVERGENCE,
            "max_iterations esgotado sem satisfazer a tolerancia dupla",
            iterations=iterations, bracket=(lo, hi), residuals=(f_mid, hi - lo),
            expansions=expansions)
    vega_raw = at_solution.greeks.vega_per_pct_point * 100.0
    if vega_raw < cfg.low_vega_threshold:
        status = IvStatus.LOW_VEGA
        message = ("convergiu, mas vega abaixo de low_vega_threshold: "
                   "sigma mal condicionado")
    else:
        status = IvStatus.OK
        message = "convergencia com tolerancia dupla (preco e vol)"
    diagnostic = IvDiagnostic(status, iterations, lo, hi, f_mid, hi - lo, vega_raw,
                              expansions, message)
    return IvResult(mid, diagnostic)
