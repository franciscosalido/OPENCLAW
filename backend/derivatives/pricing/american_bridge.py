"""Preço de um contrato americano nas árvores CRR da série, com volatilidade dada."""

from collections.abc import Mapping
from decimal import Decimal

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
    spot_value = float("nan") if spot.is_snan() else float(spot)
    strike = float(contract.strike)
    years = tte.year_fraction
    echo: dict[str, str | float] = {
        "symbol": contract.symbol, "kind": contract.kind.value,
        "exercise_style": contract.exercise_style.value, "spot": spot_value, "strike": strike,
        "time_years": years, "rate_cont": rate_cont, "sigma": sigma,
        "dividend_yield": "unresolved", "steps": float(Decimal(steps)),
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

    price = american_n
    european = (european_n + european_n1) / 2
    echo.update(price_steps_n=american_n, price_steps_n1=american_n1, european_same_trees=european)
    merged = dict(assumptions)
    merged.update(resolved.assumptions())
    merged.update(pricing_model=AMERICAN_MODEL, crr_steps=float(steps), crr_pair_average=True,
                  early_exercise_premium=price - european)
    return PricingOutcome(
        supported=True, reason=None, model=AMERICAN_MODEL, price=Decimal(str(price)), greeks=None,
        regime="expiry" if years == 0.0 else "tree", sigma_source="given",
        inputs_echo=echo, assumptions=merged,
    )
