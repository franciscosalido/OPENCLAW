"""DL-PR05b: ``OplabMarketClient`` — modelos tipados e procedencia pelo adaptador."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.errors import ForbiddenRouteError, NotFoundError
from backend.derivatives.oplab.routes import MarketRoute, render_route
from backend.derivatives.oplab.transport import FixtureTransport, VendorResponse
from backend.derivatives.oplab.vendor_models import (
    VendorInterestRate,
    VendorMarketStatus,
    VendorOption,
    VendorPayloadError,
    VendorStock,
)
from backend.derivatives.provenance import Provenance, ProvenanceStamp, Purpose

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
DOCUMENTAL = Path("tests/fixtures/derivatives/documental")
SOURCE = "oplab-v3:"


class StubTransport:
    """Transporte minimo que devolve um payload fixo com a procedencia pedida."""

    def __init__(self, payload: object, provenance: Provenance) -> None:
        self.payload = payload
        self.provenance = provenance
        self.calls = 0

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        self.calls += 1
        rendered = render_route(route, **params)
        return VendorResponse(200, self.payload, {}, now, rendered, self.provenance)


def _client() -> OplabMarketClient:
    return OplabMarketClient(FixtureTransport(DOCUMENTAL), stamp_source=SOURCE)


def _assert_documental(stamp: ProvenanceStamp, route: str) -> None:
    assert stamp.provenance is Provenance.DOCUMENTAL
    assert stamp.purpose is Purpose.TEST
    assert stamp.source == SOURCE + route
    assert stamp.captured_at == NOW


async def test_options_chain_returns_vendor_options_and_test_stamp() -> None:
    options, stamp = await _client().options_chain("PETR3", now=NOW)
    assert isinstance(options, tuple) and len(options) == 1
    assert isinstance(options[0], VendorOption)
    assert options[0].symbol == "PETRE100"
    assert options[0].maturity_type == "AMERICAN"
    _assert_documental(stamp, "/market/options/PETR3")


async def test_stock_carries_quotation_form() -> None:
    stock, stamp = await _client().stock("PETR4", now=NOW)
    assert isinstance(stock, VendorStock)
    assert stock.quotation_form == 100
    assert stock.contract_size == 100
    _assert_documental(stamp, "/market/stocks/PETR4")


async def test_interest_rates_and_market_status() -> None:
    client = _client()
    rates, rates_stamp = await client.interest_rates(now=NOW)
    status, status_stamp = await client.market_status(now=NOW)
    assert [rate.uid for rate in rates] == ["CETIP", "SELIC"]
    assert all(isinstance(rate, VendorInterestRate) for rate in rates)
    assert isinstance(status, VendorMarketStatus)
    assert status.market_status == "N"
    _assert_documental(rates_stamp, "/market/interest_rates")
    _assert_documental(status_stamp, "/market/status")


async def test_observed_transport_yields_production_purpose() -> None:
    stub = StubTransport({"market_status": "A"}, Provenance.OBSERVED)
    _status, stamp = await OplabMarketClient(stub, stamp_source=SOURCE).market_status(now=NOW)
    assert stamp.provenance is Provenance.OBSERVED
    assert stamp.purpose is Purpose.PRODUCTION
    assert stub.calls == 1


@pytest.mark.parametrize("provenance", [Provenance.SYNTHETIC, Provenance.REPLAY])
async def test_payload_never_defines_provenance(provenance: Provenance) -> None:
    payload = {"market_status": "A", "provenance": "observed", "purpose": "production"}
    stub = StubTransport(payload, provenance)
    _status, stamp = await OplabMarketClient(stub, stamp_source=SOURCE).market_status(now=NOW)
    assert stamp.provenance is provenance
    assert stamp.purpose is Purpose.TEST


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("options_chain", {"nao": "lista"}),
        ("options_chain", [{"symbol": "PETRE100", "strike": "valor-secreto-123"}]),
        ("stock", ["lista"]),
        ("stock", {"bid": 1.0}),
        ("interest_rates", {"uid": "SELIC"}),
        ("interest_rates", [{"uid": "SELIC", "name": "x", "value": "valor-secreto-123"}]),
        ("market_status", "texto"),
        ("market_status", {"server_time": "2021-05-07T17:49:07-03:00"}),
    ],
)
async def test_malformed_payload_is_a_sanitized_vendor_error(
    method: str, payload: object,
) -> None:
    client = OplabMarketClient(StubTransport(payload, Provenance.SYNTHETIC),
                               stamp_source=SOURCE)
    with pytest.raises(VendorPayloadError) as raised:
        if method in ("options_chain", "stock"):
            await getattr(client, method)("PETR4", now=NOW)
        else:
            await getattr(client, method)(now=NOW)
    assert "valor-secreto-123" not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_typed_transport_errors_propagate_unchanged() -> None:
    with pytest.raises(NotFoundError):
        await _client().stock("VALE3", now=NOW)
    with pytest.raises(ForbiddenRouteError):
        await _client().options_chain("petr4", now=NOW)


async def test_no_method_returns_raw_json() -> None:
    client = _client()
    results = [
        (await client.options_chain("PETR3", now=NOW))[0],
        (await client.stock("PETR4", now=NOW))[0],
        (await client.interest_rates(now=NOW))[0],
        (await client.market_status(now=NOW))[0],
    ]
    for result in results:
        assert not isinstance(result, dict | list | str)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), "1e999"])
async def test_client_refuses_nonfinite_market_fields(value) -> None:
    stub = StubTransport({"symbol": "BOVA11", "close": value}, Provenance.SYNTHETIC)
    with pytest.raises(VendorPayloadError) as error:
        await OplabMarketClient(stub, stamp_source=SOURCE).stock("BOVA11", now=NOW)
    assert error.value.__context__ is None


@pytest.mark.parametrize("method,payload", [
    ("stock", {"symbol": "OUTRO_ATIVO"}),
    ("options_chain", [{"symbol": "TEST123", "category": "CALL", "strike": 1,
                        "due_date": "2026-11-19", "parent_symbol": "OUTRO_ATIVO"}]),
])
async def test_client_refuses_conflicting_underlying(method, payload) -> None:
    client = OplabMarketClient(StubTransport(payload, Provenance.SYNTHETIC), stamp_source=SOURCE)
    with pytest.raises(VendorPayloadError) as error:
        await getattr(client, method)("BOVA11", now=NOW)
    assert "OUTRO_ATIVO" not in str(error.value)
