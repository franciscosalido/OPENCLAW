"""Fixtures partilhadas dos testes do Laboratorio de Derivativos (DL-PR01)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.derivatives.oplab.vendor_models import (
    VendorInterestRate,
    VendorOption,
    VendorStock,
    parse_vendor_interest_rates,
    parse_vendor_options,
    parse_vendor_stock,
)
from backend.derivatives.provenance import Provenance, ProvenanceStamp, purpose_of

FIXTURES = Path("tests/fixtures/derivatives/documental")
NOW = datetime(2021, 5, 10, 22, 0, tzinfo=UTC)


def load_fixture(name: str) -> object:
    """Carrega uma fixture documental JSON do DL-PR00."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def petr3_options() -> tuple[VendorOption, ...]:
    return parse_vendor_options(load_fixture("market_options_PETR3.json"))


@pytest.fixture
def petr4_stock() -> VendorStock:
    return parse_vendor_stock(load_fixture("market_stocks_PETR4.json"))


@pytest.fixture
def vendor_rates() -> tuple[VendorInterestRate, ...]:
    return parse_vendor_interest_rates(load_fixture("market_interest_rates.json"))


@pytest.fixture
def documental_stamp() -> ProvenanceStamp:
    return ProvenanceStamp(
        provenance=Provenance.DOCUMENTAL,
        purpose=purpose_of(Provenance.DOCUMENTAL),
        source="tests/fixtures documental OpLab v3",
        captured_at=NOW,
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum teste do Lab abre socket: transporte httpx real e ``connect`` lancam."""
    import socket

    import httpx

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("teste do Laboratorio tentou abrir rede real")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _refuse)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setenv("QUIMERA_DERIV_FORBID_NETWORK", "1")
