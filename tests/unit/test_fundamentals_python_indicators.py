from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.finlib.fundamentals import (
    MARKET_DEPENDENT_INDICATORS,
    STATEMENT_ONLY_INDICATORS,
    FundamentalsIndicators,
    compute_computation_hash,
    compute_fundamentals_lineage_hash,
    compute_statement_only_indicators,
)


def _sample_statement(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_id": "00000000-0000-7000-8000-000000000001",
        "period_end": "2026-12-31",
        "net_revenue": "1000",
        "net_income": "120",
        "total_assets": "2400",
        "total_equity": "800",
        "gross_debt": "300",
        "cash_and_equivalents": "50",
        "operating_income": "160",
        "depreciation_amortization": "40",
        "shares_outstanding": "100",
    }
    payload.update(overrides)
    return payload


def test_fundamentals_indicators_is_strict_and_extra_forbid() -> None:
    indicators = FundamentalsIndicators.model_validate(
        {
            "lpa": Decimal("1.2"),
            "vpa": Decimal("8"),
            "ebitda": Decimal("200"),
            "net_revenue": Decimal("1000"),
            "net_income": Decimal("120"),
            "total_assets": Decimal("2400"),
            "total_equity": Decimal("800"),
            "net_debt": Decimal("250"),
            "roe": Decimal("0.15"),
            "roa": Decimal("0.05"),
        }
    )

    assert indicators.model_config["frozen"] is True
    assert indicators.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        FundamentalsIndicators.model_validate({"pe_ratio": Decimal("10")})


@pytest.mark.parametrize(
    "market_indicator",
    sorted(MARKET_DEPENDENT_INDICATORS),
)
def test_market_dependent_indicators_are_not_persisted(market_indicator: str) -> None:
    assert market_indicator not in STATEMENT_ONLY_INDICATORS
    with pytest.raises(ValidationError):
        FundamentalsIndicators.model_validate({market_indicator: Decimal("1")})


def test_compute_statement_only_indicators_derives_expected_values() -> None:
    indicators = compute_statement_only_indicators(_sample_statement())

    assert indicators.lpa == Decimal("1.2")
    assert indicators.vpa == Decimal("8")
    assert indicators.ebitda == Decimal("200")
    assert indicators.net_revenue == Decimal("1000")
    assert indicators.net_income == Decimal("120")
    assert indicators.total_assets == Decimal("2400")
    assert indicators.total_equity == Decimal("800")
    assert indicators.net_debt == Decimal("250")
    assert indicators.roe == Decimal("0.15")
    assert indicators.roa == Decimal("0.05")


def test_compute_statement_only_indicators_does_not_invent_missing_values() -> None:
    payload = _sample_statement(
        shares_outstanding=None,
        total_assets=None,
        total_equity=None,
        gross_debt=None,
        cash_and_equivalents=None,
    )

    indicators = compute_statement_only_indicators(payload)

    assert indicators.lpa is None
    assert indicators.vpa is None
    assert indicators.roe is None
    assert indicators.roa is None
    assert indicators.net_debt is None
    assert indicators.net_income == Decimal("120")


def test_lineage_hash_is_stable_and_changes_on_economic_fields() -> None:
    base = _sample_statement(run_id="run-a")
    same_content_new_run = _sample_statement(run_id="run-b")
    changed_income = _sample_statement(run_id="run-a", net_income="121")
    changed_period = _sample_statement(run_id="run-a", period_end="2027-12-31")

    assert compute_fundamentals_lineage_hash(base) == compute_fundamentals_lineage_hash(
        same_content_new_run
    )
    assert compute_fundamentals_lineage_hash(base) != compute_fundamentals_lineage_hash(
        changed_income
    )
    assert compute_fundamentals_lineage_hash(base) != compute_fundamentals_lineage_hash(
        changed_period
    )
    assert compute_fundamentals_lineage_hash(base).startswith("sha256:")


def test_lineage_hash_rejects_level0_fields() -> None:
    with pytest.raises(ValueError, match="Level 0"):
        compute_fundamentals_lineage_hash(_sample_statement(acquisition_price="10.00"))


def test_computation_hash_is_stable_and_changes_with_inputs() -> None:
    base = compute_statement_only_indicators(_sample_statement()).canonical_payload()
    changed = compute_statement_only_indicators(
        _sample_statement(net_income="121")
    ).canonical_payload()

    assert compute_computation_hash(base) == compute_computation_hash(dict(base))
    assert compute_computation_hash(base) != compute_computation_hash(changed)
    assert compute_computation_hash(base).startswith("sha256:")
