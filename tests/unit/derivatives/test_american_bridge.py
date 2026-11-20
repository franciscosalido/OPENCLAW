"""Contrato da ponte americana, com preços de referência do Marco 2A."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.derivatives.domain.carry import CarryAssumption, CarryKind
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_terms import AdjustmentEvidence, AdjustmentPolicy, SeriesTerms
from backend.derivatives.pricing.american_bridge import price_american_contract
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.conventions import TimeToExpiry

DAY = date(2026, 11, 19)
TTE = TimeToExpiry(252, 1.0, "synthetic", "test", 252, False)
CALL = OptionContract(
    symbol="XPTO1", underlying="XPTO", kind=OptionKind.CALL, exercise_style=ExerciseStyle.AMERICAN,
    strike=Decimal("100"), expiry=date(2027, 11, 19), contract_size=100, quotation_form=1, isin=None,
)
PUT = CALL.model_copy(update={"kind": OptionKind.PUT})
REFERENCE = (Path(__file__).resolve().parents[2] / "fixtures/derivatives/reference"
             / "crr_american_reference.json")


def _terms(policy: AdjustmentPolicy, strike: Decimal = CALL.strike) -> SeriesTerms:
    evidence = None if policy is AdjustmentPolicy.UNKNOWN else AdjustmentEvidence(
        issuer="B3", document="synthetic", version="1", published_on=DAY, symbol="XPTO1",
        effective_on=DAY, policy=policy,
    )
    return SeriesTerms(
        symbol="XPTO1", effective_on=DAY, source="test", strike=strike, contract_size=100,
        quotation_form=1, exercise_style=ExerciseStyle.AMERICAN, currency="BRL",
        adjustment_policy=policy, evidence=evidence,
    )


def _carry(q: str | None) -> CarryAssumption:
    return CarryAssumption(
        symbol="XPTO1", effective_on=DAY, source="test",
        kind=CarryKind.NONE if q is None else CarryKind.CONTINUOUS_YIELD,
        dividend_yield=None if q is None else Decimal(q),
    )


A1_TERMS = _terms(AdjustmentPolicy.UNPROTECTED)
A2_TERMS = _terms(AdjustmentPolicy.UNKNOWN)
YIELD = _carry("0.08")
NONE = _carry(None)


def _price(
    contract: OptionContract = CALL, *, terms: SeriesTerms = A1_TERMS,
    carry: CarryAssumption | None = YIELD, spot: Decimal = Decimal("100"), rate_cont: float = 0.05,
    sigma: float = 0.2, tte: TimeToExpiry = TTE, steps: int = 200,
    assumptions: dict[str, str | float | bool] | None = None,
) -> PricingOutcome:
    return price_american_contract(
        contract, terms=terms, carry=carry, spot=spot, rate_cont=rate_cont,
        sigma=sigma, tte=tte, steps=steps, assumptions={} if assumptions is None else assumptions,
    )


@pytest.mark.parametrize(("contract", "terms", "carry", "ids"), [
    (CALL, A1_TERMS, YIELD, ("crr_06_call_yield", "crr_07_call_yield")),
    (PUT, A2_TERMS, NONE, ("crr_16_put_rate", "crr_17_put_rate")),
], ids=["A1", "A2"])
def test_t1_anchors(contract: OptionContract, terms: SeriesTerms, carry: CarryAssumption,
                    ids: tuple[str, str]) -> None:
    """Compara preço e prêmio com as médias decimais das duas árvores da referência."""
    cases = {row["case_id"]: row for row in json.loads(REFERENCE.read_bytes())["cases"]}
    american = sum(Decimal(cases[key]["american_price"]) for key in ids) / 2
    european = sum(Decimal(cases[key]["european_price"]) for key in ids) / 2
    outcome = _price(contract, terms=terms, carry=carry)
    assert outcome.supported and outcome.reason is None and outcome.price is not None
    assert abs(outcome.price - american) <= Decimal("1e-11") * max(1, american)
    premium = outcome.assumptions["early_exercise_premium"]
    assert isinstance(premium, float) and abs(premium - float(american - european)) <= 1e-9
    assert (outcome.model, outcome.regime, outcome.sigma_source) == (
        "crr_american_v1", "tree", "given",
    )
    assert outcome.greeks is None and outcome.iv is None
