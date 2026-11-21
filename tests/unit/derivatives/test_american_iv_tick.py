"""Identificabilidade da VI americana na unidade de preço por ação."""
import asyncio
import math
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from backend.derivatives.pricing.american_bridge import AmericanIvRefusal
from backend.derivatives.pricing.implied_vol import price_bounds
from config.american_iv_config_model import load_american_iv_config
from tests.unit.derivatives import test_offline_american_demo as demo
from tests.unit.derivatives import test_quantlib_oracle as oracle
from tests.unit.derivatives.test_fd_american_iv import _iv_with


@pytest.mark.parametrize("engine", ["tree", "fd"])
@pytest.mark.parametrize("case_id", ["B21", "C01"])
def test_near_intrinsic(engine: str, case_id: str) -> None:
    """T1/T2: o preço de referência não distingue uma VI do limite."""
    row = next(case for case in oracle._CASES if case.id == case_id)
    _check(engine, row, True)


def _check(engine: str, row: oracle._Case, refused: bool) -> None:
    if engine == "tree":
        tree = oracle._tree_iv(row)
        if refused:
            assert isinstance(tree, AmericanIvRefusal)
            assert tree.reason == "iv:not_identifiable" and tree.sigma is None
        else:
            assert not isinstance(tree, AmericanIvRefusal) or tree.reason != "iv:not_identifiable"
    else:
        fd = oracle._fd_iv(row)
        assert (fd.status == "not_identifiable") == refused
        if refused:
            assert fd.sigma is None


@pytest.mark.parametrize("engine", ["tree", "fd"])
@pytest.mark.parametrize("scale", [1 - 1e-6, 1 + 1e-6])
def test_tick_boundary(engine: str, scale: float) -> None:
    """T3: a fronteira usa distância estritamente menor que um tick."""
    row = next(case for case in oracle._CASES if case.id == "B21")
    _check(engine, replace(row, american=row.intrinsic + .01 * scale), scale < 1)


@pytest.mark.parametrize("engine", ["tree", "fd"])
def test_binding_european_bound(engine: str) -> None:
    """T4: o piso europeu domina o exercício imediato na call sem proventos."""
    row = next(case for case in oracle._CASES if case.id == "A13")
    floor, _ = price_bounds(**row.inputs)
    assert row.kind == "CALL" and row.dividend_yield == 0 and floor > row.intrinsic + .01
    _check(engine, replace(row, american=floor + .005), True)


def test_small_configured_tick_recovers_b21(monkeypatch: pytest.MonkeyPatch) -> None:
    """T5: a mesma cotação volta a identificar sigma com resolução suficiente."""
    cfg = oracle._IV.model_copy(update={"price_tick": 1e-12})
    monkeypatch.setattr(oracle, "_IV", cfg)
    row = next(case for case in oracle._CASES if case.id == "B21")
    tree = oracle._tree_iv.__wrapped__(row)
    fd = oracle._fd_iv.__wrapped__(row)
    assert isinstance(tree, oracle.AmericanIvSolution) and tree.sigma > 0
    assert fd.status == "ok" and fd.sigma is not None


@pytest.mark.parametrize("value", [None, 0., -.01, 1])
def test_tick_yaml(tmp_path: Path, value: float | int | None) -> None:
    """T6: o perfil exige um tick de ponto flutuante positivo."""
    config = oracle._IV.model_dump()
    if value is None:
        del config["price_tick"]
    else:
        config["price_tick"] = value
    path = tmp_path / "tick.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValidationError, match="price_tick"):
        load_american_iv_config(path)


@pytest.mark.parametrize(("field", "value"), [
    ("price_tick", 0.), ("price_tick", -.01), ("price_tick", math.nan),
    ("price_tick", math.inf), ("price_tick", -math.inf), ("lower_bound", -.01),
    ("lower_bound", math.nan), ("lower_bound", math.inf), ("lower_bound", -math.inf),
])
def test_invalid_fd_inputs(field: str, value: float) -> None:
    """T7: entradas inválidas geram recusa tipada sem VI."""
    result = _iv_with(**{field: value})
    assert result.status == "invalid_input" and result.sigma is None


def test_demo_quote_within_one_tick(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """T8: a linha americana explica por que os três lados ficaram sem VI."""
    captured, _ = asyncio.run(demo._capture_before_american_projection())
    assert captured.time_to_expiry is not None
    years = captured.time_to_expiry.year_fraction
    price = -150. * math.expm1(-math.log1p(.149) * years) + .005
    changed = demo.quote_change({"bid": price, "ask": price})
    demo.substitute_read(monkeypatch, demo.OPTIONS_FILE, changed)
    rc, reply = demo.invoke([*demo.DEMO, *demo.OPTIONS], capsys)
    row = next(item for item in reply["data"]["rows"] if item["symbol"] == "SYNAC150")
    assert rc == 0 and row["supported"] is False
    assert row["reason"] == "iv_unavailable:bid:iv:not_identifiable"
    assert all(side == {"sigma": None, "status": "not_applicable"} for side in row["iv"].values())


@pytest.mark.parametrize("engine", ["tree", "fd"])
def test_reviewer_exactly_one_tick_above_the_floor_is_published(engine: str) -> None:
    """Revisor: a regra é estrita; cotação a exatamente um tick do piso ainda tem VI."""
    row = next(case for case in oracle._CASES if case.id == "A01")
    floor, _ = price_bounds(**row.inputs)
    assert floor == 0. and row.intrinsic == 0.
    quoted = replace(row, american=.01)
    if engine == "tree":
        tree = oracle._tree_iv(quoted)
        assert isinstance(tree, oracle.AmericanIvSolution) and tree.sigma > 0
    else:
        fd = oracle._fd_iv(quoted)
        assert fd.status == "ok" and fd.sigma is not None and fd.sigma > 0
