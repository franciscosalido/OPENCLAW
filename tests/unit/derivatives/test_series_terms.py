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
