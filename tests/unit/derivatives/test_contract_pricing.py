"""Testes da ponte dominio -> modelo (DL-PR03): recusa de americanas sem numeros,
europeia com ``Decimal`` e hipoteses auditaveis no resultado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.pricing.contract_pricing import PricingOutcome, price_contract
from backend.derivatives.pricing.conventions import TimeToExpiry
from config.derivatives_config_model import Conventions

ASSUMPTIONS: dict[str, str | float | bool] = {
    "calendar_id": "B3_LISTED_TRADING",
    "calendar_versions": "b3-2026-3.0.0",
    "day_count_calendar": "trading",
    "day_count_calendar_assumed": True,
    "interval_convention": "(D0,Dv]",
    "interval_convention_assumed": True,
    "year_basis": 252.0,
    "rate_compounding": "annual_exp_252",
    "rate_compounding_assumed": True,
    "dividend_yield": 0.0,
    "strike_adjusted_by_exchange_assumed": True,
}

GREEK_KEYS = {"delta", "gamma", "vega_per_pct_point", "theta_per_day",
              "rho_per_pct_point", "theta_basis"}


def _contract(style: ExerciseStyle, kind: OptionKind = OptionKind.CALL) -> OptionContract:
    return OptionContract(symbol="PETR4X100", underlying="PETR4", kind=kind,
                          exercise_style=style, strike=Decimal("100.00"),
                          expiry=date(2026, 12, 18), contract_size=None,
                          quotation_form=None, isin=None)


def _tte(days: int) -> TimeToExpiry:
    return TimeToExpiry(business_days=days, year_fraction=days / 252.0,
                        convention="(D0,Dv]", calendar_id="B3_LISTED_TRADING", basis=252,
                        is_expiry_day=days == 0)


def _outcome(style: ExerciseStyle, *, kind: OptionKind = OptionKind.CALL, days: int = 25,
             sigma: float = 0.3) -> PricingOutcome:
    return price_contract(_contract(style, kind), spot=Decimal("105.00"), rate_cont=0.09,
                          sigma=sigma, tte=_tte(days), cfg=Conventions(),
                          assumptions=ASSUMPTIONS)


@pytest.mark.parametrize(("style", "reason"), [
    (ExerciseStyle.AMERICAN, "american_not_supported_phase1"),
    (ExerciseStyle.UNKNOWN, "unknown_exercise_style"),
])
def test_non_european_is_refused_with_all_numeric_fields_none(
    style: ExerciseStyle, reason: str,
) -> None:
    outcome = _outcome(style)
    assert outcome.supported is False
    assert outcome.reason == reason
    assert outcome.model is None
    assert outcome.price is None
    assert outcome.greeks is None
    assert outcome.regime is None
    assert outcome.assumptions == ASSUMPTIONS
    assert "pricing_model" not in outcome.assumptions
    assert outcome.inputs_echo["exercise_style"] == style.value


@pytest.mark.parametrize(("days", "sigma"), [(25, 0.3), (0, 0.3), (25, 0.0)])
def test_american_never_receives_a_price_on_any_path(days: int, sigma: float) -> None:
    outcome = _outcome(ExerciseStyle.AMERICAN, days=days, sigma=sigma)
    assert outcome.supported is False
    assert outcome.price is None
    assert outcome.greeks is None
    assert outcome.reason == "american_not_supported_phase1"


def test_european_call_is_priced_with_decimal_and_assumptions() -> None:
    outcome = _outcome(ExerciseStyle.EUROPEAN)
    assert outcome.supported is True
    assert outcome.reason is None
    assert outcome.model == "bsm_european_v1"
    assert isinstance(outcome.price, Decimal)
    assert outcome.price > 0
    assert outcome.regime == "regular"
    assert outcome.greeks is not None
    assert set(outcome.greeks) == GREEK_KEYS
    assert outcome.greeks["theta_basis"] == 252.0
    assert outcome.assumptions == {**ASSUMPTIONS, "pricing_model": "bsm_european_v1"}
    assert outcome.inputs_echo["spot"] == 105.0
    assert outcome.inputs_echo["strike"] == 100.0
    assert outcome.inputs_echo["kind"] == "CALL"
    assert outcome.inputs_echo["symbol"] == "PETR4X100"


def test_european_expiry_day_prices_intrinsic() -> None:
    outcome = _outcome(ExerciseStyle.EUROPEAN, days=0)
    assert outcome.supported is True
    assert outcome.regime == "expiry"
    assert outcome.price == Decimal("5.0")


def test_european_put_zero_vol_regime() -> None:
    outcome = _outcome(ExerciseStyle.EUROPEAN, kind=OptionKind.PUT, sigma=0.0)
    assert outcome.supported is True
    assert outcome.regime == "zero_vol"
    assert outcome.price is not None
    assert outcome.price >= 0


def test_outcome_is_frozen_and_rejects_extra_fields() -> None:
    outcome = _outcome(ExerciseStyle.EUROPEAN)
    with pytest.raises(ValidationError):
        outcome.supported = False  # type: ignore[misc]
    with pytest.raises(ValidationError):
        PricingOutcome(supported=True, reason=None, model=None, price=None, greeks=None,
                       regime=None, inputs_echo={}, assumptions={},
                       extra_field=True)  # type: ignore[call-arg]
