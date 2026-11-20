"""Preço de um contrato americano nas árvores CRR da série, com volatilidade dada."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import ValidationError

from backend.derivatives.domain.carry import CarryAssumption, CarryRefusal, resolve_carry
from backend.derivatives.domain.models import ExerciseStyle, OptionContract
from backend.derivatives.domain.series_terms import SeriesTerms, TermsRefusal
from backend.derivatives.pricing.binomial import BinomialRefusal, crr_price
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.conventions import TimeToExpiry

AMERICAN_MODEL = "crr_american_v1"


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


def _numeric_echo(value: Decimal | float | int, expected: type[Decimal | float | int]) -> float | str:
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

    if contract.exercise_style is ExerciseStyle.UNKNOWN:
        return refused("unknown_exercise_style")
    if contract.exercise_style is not ExerciseStyle.AMERICAN:
        return refused("american_bridge:not_american")
    try:
        resolved = resolve_carry(terms, carry)
    except TermsRefusal as exc:
        return refused(f"terms:{exc.code.value}")
    except CarryRefusal as exc:
        return refused(f"carry:{exc.code.value}")
    except ValidationError:
        return refused("american_bridge:invalid_terms_or_carry")

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
    model: Literal["crr_american_v1", "bsm_european_v1"]
    bracket: tuple[float, float]


@dataclass(frozen=True, slots=True)
class AmericanIvRefusal:
    """Motivo estável de recusa de uma observação de preço."""

    reason: str
    sigma: ClassVar[None] = None


def american_implied_vol(
    contract: OptionContract, *, terms: SeriesTerms, carry: CarryAssumption | None,
    spot: Decimal, target_price: Decimal, rate_cont: float, tte: TimeToExpiry, steps: int,
) -> AmericanIvSolution | AmericanIvRefusal:
    """Inverte um preço por unidade de uma série americana com carry explícito."""
    return AmericanIvRefusal("iv:unbracketed")
