from datetime import date
from decimal import Decimal

import pytest

from backend.derivatives.domain.models import ExerciseStyle
from backend.derivatives.domain.series_terms import AdjustmentPolicy, SeriesTerms, TermsRefusal


def sample():
    return dict(symbol="SYNX63", effective_on=date(2026, 1, 5), source="fixture A",
                strike=Decimal("1.234567890123456789012345678901234567890"),
                contract_size=37, quotation_form=1000, currency="BRL",
                exercise_style=ExerciseStyle.EUROPEAN, adjustment_policy=AdjustmentPolicy.UNKNOWN)


def test_missing_contract_size():
    fields = sample()
    del fields["contract_size"]
    with pytest.raises(TermsRefusal) as refusal:
        SeriesTerms(**fields)
    assert refusal.value.code == "missing_contract_size"


@pytest.mark.parametrize(("field", "code", "invalid"), [
    ("contract_size", "missing_contract_size", [None, 0, -1, True, 37.0, "37"]),
    ("quotation_form", "missing_quotation_form", [None, 0, 37, True, 1.0, "1000"]),
    ("exercise_style", "unknown_exercise_style", [None, ExerciseStyle.UNKNOWN, "?", True]),
    ("currency", "unknown_currency", [None, "XYZ", "", True]),
])
def test_refusal_in_isolation(field, code, invalid):
    fields = sample()
    del fields[field]
    for change in [{}, *({field: value} for value in invalid)]:
        with pytest.raises(TermsRefusal) as refusal:
            SeriesTerms(**(fields | change))
        assert refusal.value.code == code


@pytest.mark.parametrize("factor", [1, 1000])
def test_independent_lot_and_effective_strike(factor):
    first = SeriesTerms(**(sample() | {"quotation_form": factor}))
    later = SeriesTerms(**(sample() | dict(effective_on=date(2026, 1, 6), strike=Decimal("176"),
                                          exercise_style=ExerciseStyle.AMERICAN)))
    assert (first.contract_size, first.quotation_form) == (37, factor)
    assert first.strike.as_tuple() == sample()["strike"].as_tuple()
    assert first.symbol == later.symbol and first.effective_on < later.effective_on
    assert later.strike == Decimal("176")
    assert first.adjustment_policy is AdjustmentPolicy.UNKNOWN


@pytest.mark.parametrize(("field", "value"), [
    ("strike", 1.1), ("strike", "1.1"), ("strike", 1), ("strike", Decimal("NaN")),
    ("strike", Decimal("Infinity")), ("strike", Decimal("-0")),
    ("source", "  "), ("symbol", ""), ("effective_on", None), ("effective_on", "2026-01-05"),
    ("adjustment_policy", "MAYBE"),
])
def test_invalid_metadata(field, value):
    with pytest.raises(ValueError):
        SeriesTerms(**(sample() | {field: value}))


def evidence(policy):
    return dict(issuer="B3", document="fixture sintética, seção 2", version="rev1",
                published_on=date(2026, 1, 2), symbol="SYNX63",
                effective_on=date(2026, 1, 5), policy=policy)


@pytest.mark.parametrize("policy", [AdjustmentPolicy.PROTECTED, AdjustmentPolicy.UNPROTECTED])
def test_conclusive_policy_requires_matching_evidence(policy):
    fields = sample() | dict(adjustment_policy=policy)
    with pytest.raises(ValueError):
        SeriesTerms(**fields)
    doc = evidence(policy)
    assert SeriesTerms(**fields, evidence=doc).evidence.version == "rev1"
    for patch in [dict(issuer="vendor"), dict(version=" "), dict(document=""),
                  dict(published_on=None), dict(effective_on=date(2025, 1, 5)),
                  dict(symbol="SYNX65"), dict(policy=AdjustmentPolicy.UNKNOWN),
                  dict(policy=(AdjustmentPolicy.UNPROTECTED if policy == AdjustmentPolicy.PROTECTED
                               else AdjustmentPolicy.PROTECTED))]:
        with pytest.raises(ValueError):
            SeriesTerms(**fields, evidence=doc | patch)
