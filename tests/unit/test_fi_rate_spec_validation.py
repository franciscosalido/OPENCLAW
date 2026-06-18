from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError

from backend.finlib.rate_spec import (
    FI_INDEXERS,
    FI_KINDS,
    RateSpec,
    compute_fi_lineage_hash,
    compute_quality_flags,
    validate_rate_spec_for_instrument,
)


def test_all_private_fixed_income_kinds_are_representable() -> None:
    assert FI_KINDS == ("cdb", "lca", "lci", "cri", "cra", "debenture")


def test_all_private_fixed_income_indexers_are_representable() -> None:
    assert FI_INDEXERS == ("cdi", "ipca", "prefixado", "selic", "igpm")


def test_prefixado_rate_spec_is_valid() -> None:
    spec = RateSpec(
        indexer="prefixado",
        rate_model="prefixado",
        rate=Decimal("0.1325"),
        day_count=252,
        payment_frequency="bullet",
    )

    assert spec.rate == Decimal("0.1325")
    assert spec.spread is None
    assert spec.coupon is None


def test_percent_of_indexer_rate_spec_is_valid() -> None:
    spec = RateSpec(
        indexer="cdi",
        rate_model="percent_of_indexer",
        rate=Decimal("1.05"),
        day_count=252,
        payment_frequency="bullet",
    )

    assert spec.rate == Decimal("1.05")


def test_indexer_plus_spread_rate_spec_is_valid_for_cdi_and_selic() -> None:
    for indexer in ("cdi", "selic"):
        spec = RateSpec(
            indexer=indexer,
            rate_model="indexer_plus_spread",
            spread=Decimal("0.015"),
            day_count=252,
            payment_frequency="monthly",
        )
        assert spec.indexer == indexer
        assert spec.spread == Decimal("0.015")


def test_inflation_plus_coupon_rate_spec_is_valid_for_ipca_and_igpm() -> None:
    for indexer in ("ipca", "igpm"):
        spec = RateSpec(
            indexer=indexer,
            rate_model="inflation_plus_coupon",
            coupon=Decimal("0.061"),
            day_count=365,
            payment_frequency="annual",
        )
        assert spec.indexer == indexer
        assert spec.coupon == Decimal("0.061")


def test_rate_spec_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RateSpec.model_validate(
            {
                "indexer": "cdi",
                "rate_model": "percent_of_indexer",
                "rate": Decimal("1.05"),
                "day_count": 252,
                "payment_frequency": "bullet",
                "internal_note": "forbidden",
            }
        )


def test_rate_spec_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        RateSpec.model_validate(
            {
                "indexer": "cdi",
                "rate_model": "percent_of_indexer",
                "rate": Decimal("1.05"),
            }
        )


def test_rate_spec_rejects_human_percent_string() -> None:
    with pytest.raises(ValidationError):
        RateSpec.model_validate(
            {
                "indexer": "prefixado",
                "rate_model": "prefixado",
                "rate": "10%",
                "day_count": 252,
                "payment_frequency": "bullet",
            }
        )


def test_validate_rate_spec_rejects_column_json_indexer_divergence() -> None:
    with pytest.raises(ValueError, match="indexer mismatch"):
        validate_rate_spec_for_instrument(
            kind="cdb",
            indexer="cdi",
            rate_spec={
                "indexer": "selic",
                "rate_model": "percent_of_indexer",
                "rate": Decimal("1.0"),
                "day_count": 252,
                "payment_frequency": "bullet",
            },
        )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "indexer": "cdi",
            "rate_model": "prefixado",
            "rate": Decimal("0.12"),
            "day_count": 252,
            "payment_frequency": "bullet",
        },
        {
            "indexer": "ipca",
            "rate_model": "percent_of_indexer",
            "rate": Decimal("1.0"),
            "day_count": 252,
            "payment_frequency": "bullet",
        },
        {
            "indexer": "cdi",
            "rate_model": "inflation_plus_coupon",
            "coupon": Decimal("0.05"),
            "day_count": 252,
            "payment_frequency": "annual",
        },
    ),
)
def test_rate_model_incompatible_with_indexer_is_rejected(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RateSpec.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    (
        {
            "indexer": "cdi",
            "rate_model": "percent_of_indexer",
            "rate": Decimal("0"),
            "day_count": 252,
            "payment_frequency": "bullet",
        },
        {
            "indexer": "cdi",
            "rate_model": "percent_of_indexer",
            "rate": Decimal("5.0"),
            "day_count": 252,
            "payment_frequency": "bullet",
        },
        {
            "indexer": "prefixado",
            "rate_model": "prefixado",
            "rate": Decimal("-1"),
            "day_count": 252,
            "payment_frequency": "bullet",
        },
        {
            "indexer": "ipca",
            "rate_model": "inflation_plus_coupon",
            "coupon": Decimal("5.0"),
            "day_count": 365,
            "payment_frequency": "annual",
        },
    ),
)
def test_absurd_rate_ranges_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RateSpec.model_validate(payload)


def test_quality_flags_warn_for_unusual_but_possible_combinations() -> None:
    assert compute_quality_flags("lci", "prefixado") == {
        "warnings": ["uncommon_lci_prefixado"]
    }
    assert compute_quality_flags("lca", "prefixado") == {
        "warnings": ["uncommon_lca_prefixado"]
    }
    assert compute_quality_flags("cdb", "prefixado") == {}


def test_lineage_hash_is_stable_for_same_payload() -> None:
    payload = _lineage_payload()

    assert compute_fi_lineage_hash(payload) == compute_fi_lineage_hash(dict(payload))


def test_lineage_hash_changes_when_rate_spec_changes() -> None:
    payload = _lineage_payload()
    changed = dict(payload)
    changed_rate_spec = dict(cast(dict[str, object], payload["rate_spec_canonical"]))
    changed_rate_spec["rate"] = "1.10"
    changed["rate_spec_canonical"] = changed_rate_spec

    assert compute_fi_lineage_hash(payload) != compute_fi_lineage_hash(changed)


def test_lineage_hash_changes_when_issuer_cnpj_changes() -> None:
    payload = _lineage_payload()
    changed = dict(payload, issuer_cnpj="22222222000122")

    assert compute_fi_lineage_hash(payload) != compute_fi_lineage_hash(changed)


def test_lineage_hash_changes_when_maturity_date_changes() -> None:
    payload = _lineage_payload()
    changed = dict(payload, maturity_date=date(2031, 1, 2))

    assert compute_fi_lineage_hash(payload) != compute_fi_lineage_hash(changed)


def test_lineage_hash_rejects_level0_position_fields() -> None:
    payload = _lineage_payload()
    payload["quantity"] = Decimal("1000")
    payload["acquisition_price"] = Decimal("999.50")
    payload["cpf"] = "00000000000"

    with pytest.raises(ValueError, match="Level 0"):
        compute_fi_lineage_hash(payload)


def _lineage_payload() -> dict[str, object]:
    spec = RateSpec(
        indexer="cdi",
        rate_model="percent_of_indexer",
        rate=Decimal("1.05"),
        day_count=252,
        payment_frequency="bullet",
    )
    return {
        "isin": None,
        "kind": "cdb",
        "issuer_cnpj": "11111111000111",
        "indexer": "cdi",
        "rate_spec_canonical": spec.canonical_payload(),
        "maturity_date": date(2031, 1, 1),
        "issue_date": date(2026, 1, 1),
        "source_id": "local_fixed_income_input",
        "schema_version": 1,
    }
