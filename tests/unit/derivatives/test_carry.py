"""Contrato da premissa de carry e sua aplicação a uma série sintética."""

from datetime import date
from decimal import Decimal

import pytest

from backend.derivatives.domain.carry import (
    CarryAssumption,
    CarryKind,
    CarryRefusal,
    CarryRefusalCode,
    resolve_carry,
)
from backend.derivatives.domain.models import ExerciseStyle
from backend.derivatives.domain.series_terms import AdjustmentPolicy, SeriesTerms


SYMBOL = "SYNX63"
DAY = date(2026, 1, 5)


def _terms(policy: AdjustmentPolicy) -> SeriesTerms:
    evidence = None if policy is AdjustmentPolicy.UNKNOWN else dict(
        issuer="B3", document="documento sintético", version="1", published_on=DAY,
        symbol=SYMBOL, effective_on=DAY, policy=policy,
    )
    return SeriesTerms.model_validate(dict(
        symbol=SYMBOL, effective_on=DAY, source="fixture", strike=Decimal("180"),
        contract_size=37, quotation_form=1, currency="BRL", exercise_style=ExerciseStyle.EUROPEAN,
        adjustment_policy=policy, evidence=evidence,
    ))


def _carry(kind: CarryKind, value: Decimal | None = None) -> CarryAssumption:
    return CarryAssumption(symbol=SYMBOL, effective_on=DAY, source="fonte sintética",
                           kind=kind, dividend_yield=value)


def test_protected_refuses_continuous_yield() -> None:
    """O ajuste do strike impede contar o provento no rendimento."""
    terms = _terms(AdjustmentPolicy.PROTECTED)
    assumption = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03"))
    with pytest.raises(CarryRefusal) as error:
        resolve_carry(terms, assumption)
    assert error.value.code is CarryRefusalCode.DIVIDEND_DOUBLE_COUNT
