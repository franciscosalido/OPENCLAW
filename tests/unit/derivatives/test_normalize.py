"""Normalizacao da fixture documental PETR3 e da chain (DL-PR01).

Errata do card DL-PR01: 1620423900000 ms corresponde a 2021-05-07T21:45:00Z
(o card dizia 22:25:00; aritmetica verificada em sessao e fixada abaixo).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from loguru import logger

from backend.derivatives.adapters.normalize import (
    NormalizationError,
    contract_from_vendor,
    epoch_ms_to_datetime,
    money,
    normalize_chain,
    quote_from_vendor,
    rate_from_vendor,
    spot_from_vendor,
)
from backend.derivatives.domain.models import ExerciseStyle, OptionKind, SpotSource
from backend.derivatives.oplab.vendor_models import (
    VendorInterestRate,
    VendorOption,
    VendorStock,
)
from backend.derivatives.provenance import ProvenanceStamp, Purpose
from config.derivatives_config_model import Quality

NOW = datetime(2021, 5, 10, 22, 0, tzinfo=UTC)
EXPIRY = date(2021, 5, 21)


def test_epoch_ms_known_value() -> None:
    assert epoch_ms_to_datetime(1620423900000) == datetime(2021, 5, 7, 21, 45, tzinfo=UTC)
    assert epoch_ms_to_datetime(1620438635404) == datetime(
        2021, 5, 8, 1, 50, 35, 404000, tzinfo=UTC
    )


def test_epoch_ms_zero_and_none_are_none() -> None:
    assert epoch_ms_to_datetime(0) is None
    assert epoch_ms_to_datetime(None) is None


def test_money_is_exact_decimal() -> None:
    assert money(0.02) == Decimal("0.02")
    assert str(money(0.02)) == "0.02"
    assert money(None) is None
    assert money(0.0) == Decimal("0")


def test_quote_from_vendor_petr3(petr3_options: tuple[VendorOption, ...]) -> None:
    quote = quote_from_vendor(petr3_options[0], received_at=NOW)
    assert quote.ask is None
    assert quote.bid == Decimal("0.02")
    assert quote.last is None
    assert quote.received_at == NOW


def test_quote_from_vendor_times(petr3_options: tuple[VendorOption, ...]) -> None:
    quote = quote_from_vendor(petr3_options[0], received_at=NOW)
    assert quote.source_time == datetime(2021, 5, 7, 21, 45, tzinfo=UTC)
    assert quote.last_trade_at == datetime(2021, 5, 8, 1, 50, 35, 404000, tzinfo=UTC)


def test_contract_from_vendor_petr3(petr3_options: tuple[VendorOption, ...]) -> None:
    contract = contract_from_vendor(petr3_options[0], underlying="PETR3", quotation_form=100)
    assert contract.strike == Decimal("9.21")
    assert contract.expiry == EXPIRY
    assert contract.exercise_style is ExerciseStyle.AMERICAN
    assert contract.kind is OptionKind.CALL
    assert contract.quotation_form == 100
    assert contract.underlying == "PETR3"


def test_contract_maturity_type_none_is_unknown(
    petr3_options: tuple[VendorOption, ...],
) -> None:
    opt = petr3_options[0].model_copy(update={"maturity_type": None})
    contract = contract_from_vendor(opt, underlying="PETR3", quotation_form=None)
    assert contract.exercise_style is ExerciseStyle.UNKNOWN


def test_spot_prefers_stock_endpoint(
    petr4_stock: VendorStock, petr3_options: tuple[VendorOption, ...]
) -> None:
    spot = spot_from_vendor(petr4_stock, petr3_options)
    assert spot is not None
    assert spot.price == Decimal("24.71")
    assert spot.source is SpotSource.STOCK_ENDPOINT
    assert spot.observed_at == datetime(2021, 5, 10, 21, 0, tzinfo=UTC)


def test_spot_fallback_option_last_trade(petr3_options: tuple[VendorOption, ...]) -> None:
    spot = spot_from_vendor(None, petr3_options)
    assert spot is not None
    assert spot.price == Decimal("23.93")
    assert spot.source is SpotSource.OPTION_LAST_TRADE
    assert spot.observed_at == datetime(2021, 5, 8, 1, 50, 35, 404000, tzinfo=UTC)


def test_spot_none_without_data() -> None:
    assert spot_from_vendor(None, ()) is None


def test_rate_prefers_selic(vendor_rates: tuple[VendorInterestRate, ...]) -> None:
    rate = rate_from_vendor(vendor_rates)
    assert rate is not None
    assert rate.uid == "SELIC"
    assert rate.value_pct_aa == Decimal("3.4000915787165464")
    assert rate.compounding_assumed is True


def test_rate_fallback_first_when_preferred_absent(
    vendor_rates: tuple[VendorInterestRate, ...],
) -> None:
    rate = rate_from_vendor(vendor_rates, preferred_uid="IPCA")
    assert rate is not None
    assert rate.uid == "CETIP"


def test_rate_empty_is_none() -> None:
    assert rate_from_vendor(()) is None


def test_normalize_chain_documental(
    petr3_options: tuple[VendorOption, ...],
    petr4_stock: VendorStock,
    vendor_rates: tuple[VendorInterestRate, ...],
    documental_stamp: ProvenanceStamp,
) -> None:
    chain = normalize_chain(
        options=petr3_options,
        stock=petr4_stock,
        rates=vendor_rates,
        underlying="PETR3",
        expiry=EXPIRY,
        stamp=documental_stamp,
        now=NOW,
        quality_cfg=Quality(),
    )
    assert len(chain.rows) == 1
    assert chain.purpose is Purpose.TEST
    assert chain.acquired_at == NOW
    assert chain.model_assumptions == {}
    assert chain.schema_version == "quimera-derivatives-chain-v1"
    assert chain.spot is not None and chain.spot.source is SpotSource.STOCK_ENDPOINT
    assert chain.rate is not None and chain.rate.uid == "SELIC"


def test_normalize_chain_filters_other_expiry(
    petr3_options: tuple[VendorOption, ...],
    petr4_stock: VendorStock,
    vendor_rates: tuple[VendorInterestRate, ...],
    documental_stamp: ProvenanceStamp,
) -> None:
    chain = normalize_chain(
        options=petr3_options,
        stock=petr4_stock,
        rates=vendor_rates,
        underlying="PETR3",
        expiry=date(2021, 6, 18),
        stamp=documental_stamp,
        now=NOW,
        quality_cfg=Quality(),
    )
    assert chain.rows == ()


def test_normalize_chain_orders_rows_by_kind_and_strike(
    petr3_options: tuple[VendorOption, ...], documental_stamp: ProvenanceStamp
) -> None:
    base = petr3_options[0]
    shuffled = (
        base.model_copy(update={"category": "PUT", "symbol": "PETRQ90", "strike": 9.0}),
        base.model_copy(update={"symbol": "PETRE120", "strike": 12.0}),
        base.model_copy(update={"symbol": "PETRE80", "strike": 8.0}),
    )
    chain = normalize_chain(
        options=shuffled,
        stock=None,
        rates=(),
        underlying="PETR3",
        expiry=EXPIRY,
        stamp=documental_stamp,
        now=NOW,
        quality_cfg=Quality(),
    )
    ordered = [(row.contract.kind, row.contract.strike) for row in chain.rows]
    assert ordered == [
        (OptionKind.CALL, Decimal("8")),
        (OptionKind.CALL, Decimal("12")),
        (OptionKind.PUT, Decimal("9")),
    ]


def test_normalize_chain_rejects_naive_now(
    petr3_options: tuple[VendorOption, ...], documental_stamp: ProvenanceStamp
) -> None:
    with pytest.raises(NormalizationError):
        normalize_chain(
            options=petr3_options,
            stock=None,
            rates=(),
            underlying="PETR3",
            expiry=EXPIRY,
            stamp=documental_stamp,
            now=datetime(2021, 5, 10, 22, 0),
            quality_cfg=Quality(),
        )


def test_unknown_vendor_field_warns_once_per_name(
    documental_stamp: ProvenanceStamp,
) -> None:
    raw = json.loads(
        Path("tests/fixtures/derivatives/documental/market_options_PETR3.json").read_text(
            encoding="utf-8"
        )
    )[0]
    noisy = VendorOption.model_validate({**raw, "campo_inesperado": 1})
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        normalize_chain(
            options=(noisy, noisy),
            stock=None,
            rates=(),
            underlying="PETR3",
            expiry=EXPIRY,
            stamp=documental_stamp,
            now=NOW,
            quality_cfg=Quality(),
        )
    finally:
        logger.remove(sink_id)
    assert sum("campo_inesperado" in message for message in messages) == 1
