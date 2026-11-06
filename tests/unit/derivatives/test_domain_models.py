"""Contratos dos modelos de dominio (DL-PR01): forbid, frozen, Decimal, anti-naive."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from backend.derivatives.domain.models import (
    Chain,
    Quote,
    SpotObservation,
    SpotSource,
)
from backend.derivatives.provenance import (
    Provenance,
    ProvenanceStamp,
    Purpose,
    purpose_of,
)

NOW = datetime(2021, 5, 10, 22, 0, tzinfo=UTC)
NAIVE = datetime(2021, 5, 10, 22, 0)


def make_quote(**overrides: Any) -> Quote:
    base: dict[str, Any] = {
        "bid": Decimal("0.02"),
        "ask": Decimal("0.04"),
        "last": None,
        "bid_size": 10,
        "ask_size": 10,
        "volume": 5,
        "trades": 2,
        "last_trade_at": None,
        "source_time": NOW,
        "received_at": NOW,
    }
    base.update(overrides)
    return Quote(**base)


def make_chain(purpose: Purpose, acquired_at: datetime = NOW) -> Chain:
    stamp = ProvenanceStamp(
        provenance=Provenance.DOCUMENTAL,
        purpose=purpose_of(Provenance.DOCUMENTAL),
        source="documental",
        captured_at=NOW,
    )
    return Chain(
        underlying="PETR3",
        expiry=date(2021, 5, 21),
        spot=None,
        rate=None,
        rows=(),
        stamp=stamp,
        purpose=purpose,
        acquired_at=acquired_at,
        model_assumptions={},
    )


def test_extra_field_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        make_quote(campo_intruso=1)


def test_domain_models_are_frozen() -> None:
    quote = make_quote()
    with pytest.raises(ValidationError):
        quote.bid = Decimal("1")  # type: ignore[misc]


def test_quote_mid_requires_both_sides() -> None:
    assert make_quote().mid == Decimal("0.03")
    assert make_quote(bid=None).mid is None
    assert make_quote(ask=None).mid is None


def test_naive_received_at_rejected() -> None:
    with pytest.raises(ValidationError):
        make_quote(received_at=NAIVE)


def test_naive_observed_at_rejected_in_spot() -> None:
    with pytest.raises(ValidationError):
        SpotObservation(
            price=Decimal("24.71"), source=SpotSource.STOCK_ENDPOINT, observed_at=NAIVE
        )


def test_chain_rejects_naive_acquired_at() -> None:
    with pytest.raises(ValidationError):
        make_chain(Purpose.TEST, acquired_at=NAIVE)


def test_chain_rejects_promoted_purpose() -> None:
    with pytest.raises(ValidationError):
        make_chain(Purpose.PRODUCTION)


def test_chain_accepts_inherited_test_purpose() -> None:
    chain = make_chain(Purpose.TEST)
    assert chain.purpose is Purpose.TEST
    assert chain.schema_version == "quimera-derivatives-chain-v1"
    assert chain.stamp.provenance is Provenance.DOCUMENTAL
