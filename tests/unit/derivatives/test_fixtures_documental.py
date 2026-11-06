"""Contratos das fixtures documentais OpLab v3 e do seu manifesto de hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FIXTURES = Path("tests/fixtures/derivatives/documental")
EXPECTED_FILES = {
    "market_options_PETR3.json",
    "market_options_details_PETRE100.json",
    "market_stocks_PETR4.json",
    "market_instruments_XBOV11.json",
    "market_interest_rates.json",
    "market_status.json",
    "market_options_bs_example.json",
}
MINIMAL_CHAIN_FIELDS = {
    "bid",
    "ask",
    "strike",
    "due_date",
    "maturity_type",
    "contract_size",
    "time",
    "last_trade_at",
}


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_all_documental_fixtures_parse_as_json() -> None:
    on_disk = {p.name for p in FIXTURES.glob("*.json")} - {"manifest.json"}
    assert on_disk == EXPECTED_FILES
    for name in EXPECTED_FILES:
        assert _load(name) is not None


def test_manifest_matches_disk_both_ways() -> None:
    manifest = _load("manifest.json")
    assert manifest["provenance"] == "documental"
    assert manifest["source"] == "https://apidocs.oplab.com.br/"
    listed = set(manifest["files"])
    on_disk = {p.name for p in FIXTURES.glob("*.json")} - {"manifest.json"}
    assert on_disk - listed == set(), "arquivo no disco fora do manifesto"
    assert listed - on_disk == set(), "item do manifesto sem arquivo no disco"
    for name, entry in manifest["files"].items():
        digest = hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"hash divergente: {name}"
        assert entry["endpoint"].startswith("GET /market/")


def test_chain_option_is_american_and_preserved() -> None:
    chain = _load("market_options_PETR3.json")
    assert isinstance(chain, list)
    assert chain[0]["maturity_type"] == "AMERICAN"


def test_stock_quotation_form_is_100() -> None:
    assert _load("market_stocks_PETR4.json")["quotation_form"] == 100


def test_etf_quotation_form_is_1() -> None:
    assert _load("market_instruments_XBOV11.json")["quotation_form"] == 1


def test_chain_has_minimal_fields() -> None:
    row = _load("market_options_PETR3.json")[0]
    missing = MINIMAL_CHAIN_FIELDS - set(row)
    assert missing == set(), f"campos minimos ausentes na chain: {sorted(missing)}"


def test_bs_example_is_numerically_useless() -> None:
    assert _load("market_options_bs_example.json")["volatility"] == 0
