"""Contratos dos vendor models OpLab (DL-PR01): espelho da doc, extras em model_extra."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.derivatives.oplab.vendor_models import (
    VendorInterestRate,
    VendorOption,
    VendorPayloadError,
    parse_vendor_interest_rates,
    parse_vendor_market_status,
    parse_vendor_options,
    parse_vendor_stock,
    unknown_fields,
)

FIXTURES = Path("tests/fixtures/derivatives/documental")


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_options_fixture_parses_as_vendor_option() -> None:
    options = parse_vendor_options(load_fixture("market_options_PETR3.json"))
    assert len(options) == 1
    assert options[0].symbol == "PETRE100"
    assert options[0].category == "CALL"
    assert options[0].maturity_type == "AMERICAN"


def test_option_details_fixture_parses() -> None:
    detail = VendorOption.model_validate(load_fixture("market_options_details_PETRE100.json"))
    assert detail.parent_symbol == "PETR3"
    assert detail.contract_size == 100


def test_stock_fixture_parses_with_quotation_form() -> None:
    stock = parse_vendor_stock(load_fixture("market_stocks_PETR4.json"))
    assert stock.quotation_form == 100
    assert stock.close == 24.71


def test_instrument_fixture_parses_as_stock() -> None:
    etf = parse_vendor_stock(load_fixture("market_instruments_XBOV11.json"))
    assert etf.quotation_form == 1


def test_interest_rates_fixture_parses() -> None:
    rates = parse_vendor_interest_rates(load_fixture("market_interest_rates.json"))
    assert [rate.uid for rate in rates] == ["CETIP", "SELIC"]


def test_market_status_fixture_parses() -> None:
    status = parse_vendor_market_status(load_fixture("market_status.json"))
    assert status.market_status == "N"
    assert status.server_time is not None
    assert status.server_time.tzinfo is not None


def test_unknown_fields_sorted_with_beta_ibov() -> None:
    stock = parse_vendor_stock(load_fixture("market_stocks_PETR4.json"))
    extra = unknown_fields(stock)
    assert "beta_ibov" in extra
    assert list(extra) == sorted(extra)


def test_option_fixture_has_no_unknown_fields() -> None:
    options = parse_vendor_options(load_fixture("market_options_PETR3.json"))
    assert unknown_fields(options[0]) == ()


def test_parse_options_rejects_object_with_sanitized_message() -> None:
    with pytest.raises(VendorPayloadError) as excinfo:
        parse_vendor_options(load_fixture("market_stocks_PETR4.json"))
    message = str(excinfo.value)
    assert "esperada lista" in message
    assert "PETR4" not in message
    assert "beta_ibov" not in message


def test_parse_stock_rejects_list() -> None:
    with pytest.raises(VendorPayloadError):
        parse_vendor_stock(load_fixture("market_options_PETR3.json"))


def test_parse_rates_rejects_object() -> None:
    with pytest.raises(VendorPayloadError):
        parse_vendor_interest_rates({"uid": "SELIC"})


def test_parse_status_rejects_list() -> None:
    with pytest.raises(VendorPayloadError):
        parse_vendor_market_status([])


def test_vendor_models_are_frozen() -> None:
    rate = VendorInterestRate(name="Taxa Selic", uid="SELIC", value=3.4)
    with pytest.raises(ValidationError):
        rate.value = 4.0  # type: ignore[misc]
