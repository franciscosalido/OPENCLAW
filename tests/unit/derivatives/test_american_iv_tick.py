"""Identificabilidade da VI americana na unidade de preço por ação."""
from dataclasses import replace

import pytest

from backend.derivatives.pricing.american_bridge import AmericanIvRefusal
from backend.derivatives.pricing.implied_vol import price_bounds
from tests.unit.derivatives import test_quantlib_oracle as oracle


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
