"""DL-PR06: fixture sintetica — integridade, determinismo e coerencia interna."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from backend.derivatives.oplab.vendor_models import (
    parse_vendor_interest_rates,
    parse_vendor_market_status,
    parse_vendor_options,
    parse_vendor_stock,
    unknown_fields,
)
from scripts.derivatives_make_synthetic_fixture import (
    GENERATOR_VERSION,
    build_fixture,
    encode,
    main,
    series_symbol,
    smile_sigma,
)
from backend.derivatives.domain.models import OptionKind

SYNTHETIC = Path("tests/fixtures/derivatives/synthetic")
PARAMS = {"seed": 20261105, "underlying": "BOVA11", "expiry": date(2026, 11, 19), "n": 100,
          "style": "EUROPEAN"}


def _manifest() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(
        (SYNTHETIC / "manifest.json").read_text(encoding="utf-8"))
    return loaded


def test_manifest_declares_synthetic_test_data_and_matches_the_files() -> None:
    manifest = _manifest()
    assert manifest["provenance"] == "synthetic"
    assert manifest["purpose"] == "test"
    assert manifest["generator_version"] == GENERATOR_VERSION
    assert "nunca apresentar como mercado" in str(manifest["note"])
    files = manifest["files"]
    assert isinstance(files, dict) and len(files) == 4
    for name, entry in files.items():
        data = (SYNTHETIC / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
    on_disk = {path.name for path in SYNTHETIC.glob("*.json")} - {"manifest.json"}
    assert on_disk == set(files)
    assert (SYNTHETIC / "README.md").is_file()


def test_generator_is_deterministic_and_seed_sensitive() -> None:
    first = build_fixture(**PARAMS, root=Path.cwd())  # type: ignore[arg-type]
    second = build_fixture(**PARAMS, root=Path.cwd())  # type: ignore[arg-type]
    assert {name: encode(payload) for name, payload in first.items()} == {
        name: encode(payload) for name, payload in second.items()}
    other = build_fixture(**{**PARAMS, "seed": 1}, root=Path.cwd())  # type: ignore[arg-type]
    assert encode(other["market_options_BOVA11.json"]) != encode(
        first["market_options_BOVA11.json"])


def test_committed_fixture_matches_the_generator_within_one_tick() -> None:
    """Tolerante a 1 centavo: ``erfc`` pode diferir no ultimo bit entre plataformas."""
    generated = build_fixture(**PARAMS, root=Path.cwd())  # type: ignore[arg-type]
    for name, payload in generated.items():
        committed = json.loads((SYNTHETIC / name).read_text(encoding="utf-8"))
        if name != "market_options_BOVA11.json":
            assert committed == payload, name
            continue
        assert isinstance(payload, list) and len(committed) == len(payload) == 100
        for mine, theirs in zip(payload, committed, strict=True):
            assert mine.keys() == theirs.keys()
            for key, value in mine.items():
                if key in ("bid", "ask", "close"):
                    assert abs(value - theirs[key]) <= 0.0100001, (mine["symbol"], key)
                else:
                    assert value == theirs[key], (mine["symbol"], key)


def test_synthetic_chain_is_internally_coherent() -> None:
    options = parse_vendor_options(
        json.loads((SYNTHETIC / "market_options_BOVA11.json").read_text(encoding="utf-8")))
    assert len(options) == 100
    assert {option.maturity_type for option in options} == {"EUROPEAN"}
    assert {option.due_date for option in options} == {date(2026, 11, 19)}
    assert sum(option.category == "CALL" for option in options) == 50
    assert len({option.symbol for option in options}) == 100
    assert len({option.time for option in options}) == 1
    for option in options:
        assert option.bid is not None and option.ask is not None
        assert 0.0 < option.bid < option.ask
        assert option.contract_size == 100
        assert unknown_fields(option) == ()
        assert option.last_trade_at is not None and option.time is not None
        assert option.last_trade_at <= option.time
    stock = parse_vendor_stock(
        json.loads((SYNTHETIC / "market_stocks_BOVA11.json").read_text(encoding="utf-8")))
    assert stock.quotation_form == 1 and stock.close == 150.0
    assert stock.time == options[0].time
    assert unknown_fields(stock) == ()
    rates = parse_vendor_interest_rates(
        json.loads((SYNTHETIC / "market_interest_rates.json").read_text(encoding="utf-8")))
    assert {rate.uid for rate in rates} == {"CETIP", "SELIC"}
    status = parse_vendor_market_status(
        json.loads((SYNTHETIC / "market_status.json").read_text(encoding="utf-8")))
    assert status.server_time is not None


def test_smile_and_symbols_are_what_the_tests_assume() -> None:
    assert smile_sigma(150.0, 150.0) == 0.22
    assert smile_sigma(140.0, 150.0) > smile_sigma(150.0, 150.0)
    assert series_symbol("BOVA11", OptionKind.CALL, date(2026, 11, 19), 137.5) == "BOVAK1375"
    assert series_symbol("BOVA11", OptionKind.PUT, date(2026, 11, 19), 162.0) == "BOVAW1620"


def test_cli_writes_a_complete_fixture_into_a_directory(tmp_path: Path) -> None:
    out = tmp_path / "synthetic"
    assert main(["--out", str(out), "--n", "4", "--style", "AMERICAN"]) == 0
    names = {path.name for path in out.iterdir()}
    assert names == {"manifest.json", "market_options_BOVA11.json", "market_status.json",
                     "market_stocks_BOVA11.json", "market_interest_rates.json"}
    options = json.loads((out / "market_options_BOVA11.json").read_text(encoding="utf-8"))
    assert len(options) == 4
    assert {option["maturity_type"] for option in options} == {"AMERICAN"}


@pytest.mark.parametrize("n", [0, -2, 3])
def test_generator_refuses_odd_or_non_positive_sizes(n: int) -> None:
    with pytest.raises(ValueError, match="par e positivo"):
        build_fixture(**{**PARAMS, "n": n}, root=Path.cwd())  # type: ignore[arg-type]
