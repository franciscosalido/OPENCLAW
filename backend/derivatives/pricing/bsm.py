"""Coprocessador BSM (DL-PR03): preco e gregas de opcoes europeias, puro e deterministico.

Unidades no nome do campo (ADR-0023): ``vega_per_pct_point``, ``rho_per_pct_point`` e
``theta_per_day`` (theta = dP/dt no calendario; anual dividido por ``theta_basis``).
Regimes ``expiry`` (T == 0) e ``zero_vol`` (sigma == 0, T > 0) sao tratados a parte,
sem divisao por ``sqrt(T) == 0``; americanas e estilo desconhecido sao recusados.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from backend.derivatives.domain.models import ExerciseStyle, OptionKind

Regime = Literal["regular", "expiry", "zero_vol"]


class PricingModel(StrEnum):
    """Modelos de precificacao suportados pelo Laboratorio."""

    BSM_EUROPEAN = "bsm_european_v1"


class PricingDomainError(ValueError):
    """Entrada fora do dominio numerico do modelo BSM."""


@dataclass(frozen=True, slots=True)
class BsmInputs:
    """Entradas do BSM: taxa e dividendo continuos, sigma anualizado em fracao decimal."""

    kind: OptionKind
    spot: float
    strike: float
    time_years: float
    rate_cont: float
    sigma: float
    dividend_yield: float = 0.0

    def __post_init__(self) -> None:
        """Valida o dominio numerico; violacao levanta ``PricingDomainError``."""
        numbers = (self.spot, self.strike, self.time_years, self.rate_cont, self.sigma,
                   self.dividend_yield)
        if not all(math.isfinite(value) for value in numbers):
            raise PricingDomainError(f"entrada nao finita no BSM: {numbers}")
        if self.spot <= 0.0 or self.strike <= 0.0:
            raise PricingDomainError("spot e strike devem ser estritamente positivos")
        if self.time_years < 0.0 or self.sigma < 0.0 or self.dividend_yield < 0.0:
            raise PricingDomainError(
                "time_years, sigma e dividend_yield nao podem ser negativos"
            )


@dataclass(frozen=True, slots=True)
class Greeks:
    """Gregas por unidade da opcao, com a unidade declarada no nome do campo."""

    delta: float
    gamma: float
    vega_per_pct_point: float
    theta_per_day: float
    rho_per_pct_point: float
    theta_basis: int


@dataclass(frozen=True, slots=True)
class BsmResult:
    """Resultado auditavel: preco, gregas, d1/d2 e o regime efetivamente aplicado."""

    model: PricingModel
    price: float
    greeks: Greeks
    d1: float | None
    d2: float | None
    regime: Regime
    notes: tuple[str, ...]


def norm_cdf(x: float) -> float:
    """CDF da normal padrao via ``math.erf`` (zero dependencias novas, ADR-0023)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """Densidade da normal padrao."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def unsupported(contract_style: ExerciseStyle) -> str:
    """Motivo de recusa para estilos sem modelo na Fase 1 (ADR-0023, decisao 4)."""
    if contract_style is ExerciseStyle.AMERICAN:
        return "american_not_supported_phase1"
    return "unknown_exercise_style"


def _expiry(inp: BsmInputs, basis: int) -> BsmResult:
    """Regime ``expiry``: intrinseco puro; delta +-0.5 em S == K e convencao declarada."""
    if inp.kind is OptionKind.CALL:
        value = max(inp.spot - inp.strike, 0.0)
        delta = 1.0 if inp.spot > inp.strike else 0.5 if inp.spot == inp.strike else 0.0
    else:
        value = max(inp.strike - inp.spot, 0.0)
        delta = -1.0 if inp.spot < inp.strike else -0.5 if inp.spot == inp.strike else 0.0
    greeks = Greeks(delta, 0.0, 0.0, 0.0, 0.0, basis)
    return BsmResult(PricingModel.BSM_EUROPEAN, value, greeks, None, None, "expiry",
                     ("expiry_day_intrinsic",))


def _analytic(inp: BsmInputs, basis: int, n_d1: float, n_d2: float, pdf_d1: float,
              d1: float | None, d2: float | None, regime: Regime,
              notes: tuple[str, ...]) -> BsmResult:
    """Formulas BSM com ``q``; nos limites chegam ``n_d1``/``n_d2`` saturados e pdf 0."""
    t = inp.time_years
    df_q = math.exp(-inp.dividend_yield * t)
    df_r = math.exp(-inp.rate_cont * t)
    sqrt_t = math.sqrt(t)
    diffusion = inp.spot * df_q * pdf_d1
    if inp.kind is OptionKind.CALL:
        value = inp.spot * df_q * n_d1 - inp.strike * df_r * n_d2
        delta = df_q * n_d1
        carry = (inp.dividend_yield * inp.spot * df_q * n_d1
                 - inp.rate_cont * inp.strike * df_r * n_d2)
        rho_raw = inp.strike * t * df_r * n_d2
    else:
        value = inp.strike * df_r * (1.0 - n_d2) - inp.spot * df_q * (1.0 - n_d1)
        delta = df_q * (n_d1 - 1.0)
        carry = (inp.rate_cont * inp.strike * df_r * (1.0 - n_d2)
                 - inp.dividend_yield * inp.spot * df_q * (1.0 - n_d1))
        rho_raw = -inp.strike * t * df_r * (1.0 - n_d2)
    gamma = diffusion / (inp.spot * inp.spot * inp.sigma * sqrt_t) if diffusion > 0.0 else 0.0
    theta_annual = carry - diffusion * inp.sigma / (2.0 * sqrt_t)
    greeks = Greeks(delta, gamma, diffusion * sqrt_t * 0.01, theta_annual / basis,
                    rho_raw * 0.01, basis)
    return BsmResult(PricingModel.BSM_EUROPEAN, value, greeks, d1, d2, regime, notes)


def price(inputs: BsmInputs, *, theta_basis: Literal[252, 365]) -> BsmResult:
    """Preco e gregas BSM de uma europeia; regimes ``expiry`` e ``zero_vol`` a parte."""
    if inputs.time_years == 0.0:
        return _expiry(inputs, theta_basis)
    if inputs.sigma == 0.0:
        forward_gap = (inputs.spot * math.exp(-inputs.dividend_yield * inputs.time_years)
                       - inputs.strike * math.exp(-inputs.rate_cont * inputs.time_years))
        n_limit = 1.0 if forward_gap > 0.0 else 0.5 if forward_gap == 0.0 else 0.0
        return _analytic(inputs, theta_basis, n_limit, n_limit, 0.0, None, None,
                         "zero_vol", ("zero_volatility_limit",))
    sqrt_t = math.sqrt(inputs.time_years)
    sigma_sqrt_t = inputs.sigma * sqrt_t
    d1 = ((math.log(inputs.spot / inputs.strike)
           + (inputs.rate_cont - inputs.dividend_yield + 0.5 * inputs.sigma * inputs.sigma)
           * inputs.time_years) / sigma_sqrt_t)
    d2 = d1 - sigma_sqrt_t
    return _analytic(inputs, theta_basis, norm_cdf(d1), norm_cdf(d2), norm_pdf(d1), d1, d2,
                     "regular", ())
