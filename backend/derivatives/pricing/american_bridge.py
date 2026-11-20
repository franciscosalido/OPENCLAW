"""Preço CRR e inversão de um preço observado de uma série americana."""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Final, Literal

from pydantic import ValidationError

from backend.derivatives.domain.carry import (
    CarryAssumption, CarryRefusal, ResolvedCarry, resolve_carry,
)
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_terms import SeriesTerms, TermsRefusal
from backend.derivatives.pricing.binomial import BinomialRefusal, crr_price
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.conventions import TimeToExpiry
from backend.derivatives.pricing.implied_vol import price_bounds
from config.derivatives_config_model import AmericanIvConfig

AMERICAN_MODEL: Final = "crr_american_v1"


def _resolve_series(
    contract: OptionContract, terms: SeriesTerms, carry: CarryAssumption | None,
) -> ResolvedCarry | str:
    if contract.exercise_style is ExerciseStyle.UNKNOWN:
        return "unknown_exercise_style"
    if contract.exercise_style is not ExerciseStyle.AMERICAN:
        return "american_bridge:not_american"
    try:
        return resolve_carry(terms, carry)
    except TermsRefusal as exc:
        return f"terms:{exc.code.value}"
    except CarryRefusal as exc:
        return f"carry:{exc.code.value}"
    except ValidationError:
        return "american_bridge:invalid_terms_or_carry"


def _matches(contract: OptionContract, terms: SeriesTerms) -> bool:
    return (
        contract.symbol == terms.symbol
        and contract.strike == terms.strike
        and contract.exercise_style == terms.exercise_style
        and (contract.contract_size is None or contract.contract_size == terms.contract_size)
        and (contract.quotation_form is None or contract.quotation_form == terms.quotation_form)
    )


def _pair_average(first: float, second: float) -> float:
    total = first + second
    if total == float("inf"):
        return first / 2 + second / 2
    return total / 2


def _numeric_echo(
    value: Decimal | float | int, expected: type[Decimal | float | int],
) -> float | str:
    if type(value) is not expected:
        return "invalid"
    if type(value) is Decimal and value.is_snan():
        return float("nan")
    try:
        return float(value)
    except OverflowError:
        return "invalid"


def price_american_contract(
    contract: OptionContract,
    *,
    terms: SeriesTerms,
    carry: CarryAssumption | None,
    spot: Decimal,
    rate_cont: float,
    sigma: float,
    tte: TimeToExpiry,
    steps: int,
    assumptions: Mapping[str, str | float | bool],
) -> PricingOutcome:
    """Confere estilo, carry e identidade da série antes de aplicar as árvores CRR."""
    spot_value = _numeric_echo(spot, Decimal)
    strike = float(contract.strike)
    years = tte.year_fraction
    echo: dict[str, str | float] = {
        "symbol": contract.symbol, "kind": contract.kind.value,
        "exercise_style": contract.exercise_style.value, "spot": spot_value, "strike": strike,
        "time_years": _numeric_echo(years, float), "rate_cont": _numeric_echo(rate_cont, float),
        "sigma": _numeric_echo(sigma, float), "dividend_yield": "unresolved",
        "steps": _numeric_echo(steps, int),
    }

    def refused(reason: str) -> PricingOutcome:
        return PricingOutcome(
            supported=False, reason=reason, model=None, price=None, greeks=None, regime=None,
            inputs_echo=echo, assumptions=dict(assumptions),
        )

    resolved = _resolve_series(contract, terms, carry)
    if isinstance(resolved, str):
        return refused(resolved)
    q = resolved.dividend_yield
    echo["dividend_yield"] = q
    if not _matches(contract, resolved.terms):
        return refused("american_bridge:series_terms_mismatch")
    if isinstance(spot_value, str):
        return refused("american_bridge:invalid_spot_type")

    def tree(style: ExerciseStyle, count: int) -> float:
        return crr_price(
            kind=contract.kind, style=style, spot=spot_value, strike=strike,
            time_years=years, rate_cont=rate_cont, sigma=sigma, dividend_yield=q, steps=count,
        )

    try:
        american_n = tree(ExerciseStyle.AMERICAN, steps)
        american_n1 = tree(ExerciseStyle.AMERICAN, steps + 1)
        european_n = tree(ExerciseStyle.EUROPEAN, steps)
        european_n1 = tree(ExerciseStyle.EUROPEAN, steps + 1)
    except BinomialRefusal as exc:
        return refused(f"binomial:{exc.code.value}")

    price = _pair_average(american_n, american_n1)
    european = _pair_average(european_n, european_n1)
    echo.update(price_steps_n=american_n, price_steps_n1=american_n1, european_same_trees=european)
    merged = dict(assumptions)
    merged.pop("dividend_yield", None)
    merged.pop("strike_adjusted_by_exchange_assumed", None)
    merged.update(resolved.assumptions())
    merged.update(pricing_model=AMERICAN_MODEL, crr_steps=float(steps), crr_pair_average=True,
                  early_exercise_premium=price - european)
    return PricingOutcome(
        supported=True, reason=None, model=AMERICAN_MODEL, price=Decimal(str(price)), greeks=None,
        regime="expiry" if years == 0.0 else "tree", sigma_source="given",
        inputs_echo=echo, assumptions=merged,
    )


@dataclass(frozen=True, slots=True)
class AmericanIvSolution:
    """Volatilidade anual em fração, modelo de inversão e bracket final."""

    sigma: float
    model: Literal["crr_american_v1"]
    bracket: tuple[float, float]
    iterations: int = 0
    expansions: int = 0


@dataclass(frozen=True, slots=True)
class AmericanIvRefusal:
    """Motivo estável de recusa de uma observação de preço."""

    reason: str
    sigma: ClassVar[None] = None
    iterations: int = 0
    expansions: int = 0


_IV_RESOLUTION = 1e-6


def _bisect_pair(
    pair: Callable[[float], float], target: float, tol: float, floor: float,
    cfg: AmericanIvConfig,
) -> AmericanIvSolution | AmericanIvRefusal:
    ceiling = cfg.bracket_hi
    if floor >= ceiling:
        return AmericanIvRefusal("iv:unbracketed")
    lo, hi = floor, ceiling
    low_price, high_price = pair(lo), pair(hi)
    if abs(low_price - target) <= tol or abs(high_price - target) <= tol:
        return AmericanIvRefusal("iv:not_identifiable")
    if not low_price < target < high_price:
        return AmericanIvRefusal("iv:unbracketed")

    for iteration in range(1, cfg.max_iterations + 1):
        mid = (lo + hi) / 2
        residual = pair(mid) - target
        if residual > 0:
            hi = mid
        else:
            lo = mid
        if hi - lo <= cfg.tol_vol and abs(residual) <= tol:
            left, right = mid - _IV_RESOLUTION, mid + _IV_RESOLUTION
            if (left < floor or right > ceiling
                    or target - pair(left) <= tol or pair(right) - target <= tol):
                return AmericanIvRefusal("iv:not_identifiable", iteration)
            return AmericanIvSolution(mid, AMERICAN_MODEL, (lo, hi), iteration)
    return AmericanIvRefusal("iv:no_convergence", cfg.max_iterations)


def american_implied_vol(
    contract: OptionContract, *, terms: SeriesTerms, carry: CarryAssumption | None,
    spot: Decimal, target_price: Decimal, rate_cont: float, tte: TimeToExpiry, steps: int,
    cfg: AmericanIvConfig,
) -> AmericanIvSolution | AmericanIvRefusal:
    """Inverte o par CRR de uma série americana com carry e configuração explícitos."""
    resolved = _resolve_series(contract, terms, carry)
    if isinstance(resolved, str):
        return AmericanIvRefusal(resolved)
    if not _matches(contract, resolved.terms):
        return AmericanIvRefusal("american_bridge:series_terms_mismatch")
    spot_value = _numeric_echo(spot, Decimal)
    if isinstance(spot_value, str):
        return AmericanIvRefusal("american_bridge:invalid_spot_type")
    years = tte.year_fraction
    if (type(rate_cont) is not float or type(years) is not float
            or type(contract.kind) is not OptionKind):
        return AmericanIvRefusal("binomial:invalid_input_type")
    strike, q = float(contract.strike), resolved.dividend_yield
    if not all(map(math.isfinite, (spot_value, strike, years, rate_cont))):
        return AmericanIvRefusal("binomial:non_finite_input")
    if type(steps) is not int or not 1 <= steps <= 4999:
        return AmericanIvRefusal("binomial:invalid_steps")
    if spot_value <= 0 or strike <= 0 or years < 0:
        return AmericanIvRefusal("binomial:input_out_of_domain")
    if (type(target_price) is not Decimal or not target_price.is_finite() or target_price < 0
            or not math.isfinite(float(target_price))):
        return AmericanIvRefusal("iv:invalid_target")
    if years == 0:
        return AmericanIvRefusal("iv:expiry")
    target = float(target_price)
    tol = cfg.tol_price_rel * max(1.0, target)
    is_call = contract.kind is OptionKind.CALL
    try:
        lower, european_upper = price_bounds(contract.kind, spot_value, strike, years, rate_cont, q)
        intrinsic = spot_value - strike if is_call else strike - spot_value
        lower = max(lower, intrinsic)
        upper = spot_value if is_call else max(strike, european_upper)
        if not math.isfinite(upper) or not math.isfinite(lower):
            return AmericanIvRefusal("iv:not_representable")
        if lower - target > tol:
            return AmericanIvRefusal("iv:below_intrinsic")
        if target - upper > tol:
            return AmericanIvRefusal("iv:above_upper_bound")
        if target - lower <= tol or upper - target <= tol:
            return AmericanIvRefusal("iv:not_identifiable")
    except (ArithmeticError, ValueError):
        return AmericanIvRefusal("iv:not_representable")

    def pair(sigma: float) -> float:
        def american(count: int) -> float:
            return crr_price(
                kind=contract.kind, style=ExerciseStyle.AMERICAN, spot=spot_value, strike=strike,
                time_years=years, rate_cont=rate_cont, dividend_yield=q, sigma=sigma, steps=count,
            )
        return _pair_average(american(steps), american(steps + 1))

    # CRR exige down < exp((r-q) dt) < up. N fixa o maior dt do par.
    floor = max(cfg.bracket_lo, abs(rate_cont - q) * math.sqrt(years / steps) + 1e-8)
    try:
        return _bisect_pair(pair, target, tol, floor, cfg)
    except BinomialRefusal as exc:
        return AmericanIvRefusal(f"binomial:{exc.code.value}")
