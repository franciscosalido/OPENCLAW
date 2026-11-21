"""Compare independent offline prices with the two frozen project engines."""
import hashlib
import json
import math
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing import bsm
from backend.derivatives.pricing.american_bridge import AmericanIvSolution, american_implied_vol
from backend.derivatives.pricing.binomial import crr_price
from backend.derivatives.pricing.fd_american import FdGrid, fd_implied_vol, fd_price
from backend.derivatives.pricing.implied_vol import price_bounds
from config.american_fd_config_model import load_american_fd_config
from config.american_iv_config_model import load_american_iv_config
from tests.unit.derivatives.test_american_bridge import A1_TERMS, CALL, TTE, _carry

_REFERENCE = Path(__file__).parents[2] / "fixtures/derivatives/reference/quantlib"
_JSON = _REFERENCE / "quantlib_reference_v1.json"
_FD = load_american_fd_config()
_IV = load_american_iv_config()
_GRID = FdGrid(_FD.space_nodes, _FD.time_steps, _FD.width_stdevs, _FD.rannacher_steps)
_EDGES = frozenset({"B21", "C01"})


@dataclass(frozen=True, slots=True)
class _Case:
    """One synthetic option and its archived price references."""

    id: str
    kind: str
    spot: float
    strike: float
    days: int
    time_years: float
    rate_cont: float
    dividend_yield: float
    sigma: float
    american: float
    european: float
    american_uncertainty: float
    american_fixed_point_a: float
    american_high_precision_scheme: float
    american_finite_differences: float

    @property
    def inputs(self) -> dict[str, object]:
        """Name the common pricing inputs."""
        return {
            "kind": OptionKind(self.kind), "spot": self.spot, "strike": self.strike,
            "time_years": self.time_years, "rate_cont": self.rate_cont,
            "dividend_yield": self.dividend_yield,
        }

    @property
    def intrinsic(self) -> float:
        """Calculate the immediate exercise value per unit."""
        return max(0., (self.spot - self.strike) * (1 if self.kind == "CALL" else -1))


_PAYLOAD = json.loads(_JSON.read_bytes())
_CASES = tuple(_Case(**row) for row in _PAYLOAD["cases"])


def _par(case, n=200):
    """Price with the production pair of adjacent trees."""
    return .5 * sum(
        crr_price(**case.inputs, style=ExerciseStyle.AMERICAN, sigma=case.sigma, steps=steps)
        for steps in (n, n + 1)
    )


def _fd(case, grid=_GRID):
    """Price with the diagnostic grid, keeping inputs identical."""
    return fd_price(**case.inputs, style=ExerciseStyle.AMERICAN, sigma=case.sigma, grid=grid)


@cache
def _tree_iv(case, steps=200):
    """Invert the archived price through the production tree bridge."""
    terms = A1_TERMS.model_copy(update={"strike": Decimal(str(case.strike))})
    contract = CALL.model_copy(update={"kind": OptionKind(case.kind), "strike": terms.strike})
    carry = _carry(str(case.dividend_yield) if case.dividend_yield else None)
    return american_implied_vol(
        contract, terms=terms, carry=carry,
        spot=Decimal(str(case.spot)), target_price=Decimal(repr(case.american)),
        rate_cont=case.rate_cont, tte=replace(TTE, year_fraction=case.time_years), steps=steps,
        cfg=_IV,
    )


@cache
def _fd_iv(case, grid=_GRID):
    """Invert the archived price through the production finite differences."""
    return fd_implied_vol(
        **case.inputs, target_price=case.american, grid=grid,
        lower_bound=max(case.intrinsic, price_bounds(**case.inputs)[0]), price_tick=_IV.price_tick,
        bracket_lo=_FD.bracket_lo, bracket_hi=_FD.bracket_hi, max_iterations=_FD.max_iterations,
        tol_price_rel=_FD.tol_price_rel, tol_vol=_FD.tol_vol,
    )


@pytest.fixture(scope="module", params=_CASES, ids=lambda case: case.id)
def case(request):
    """Share one immutable reference case with all pricing checks."""
    return request.param


@pytest.fixture(scope="module")
def tree_iv(case):
    """Share this case's tree inversion between its checks and report."""
    return _tree_iv(case)


@pytest.fixture(scope="module")
def fd_iv(case):
    """Share this case's FD inversion between its checks and report."""
    return _fd_iv(case)


def test_o1_fixture_and_generator_hashes():
    """Pin both archived inputs exactly."""
    assert hashlib.sha256(_JSON.read_bytes()).hexdigest() == (
        "c2afec8cca56175390d8c2be54bea544869251148a39363d721add1200a77281"
    )
    generator = _REFERENCE / "generate_quantlib_reference.py"
    assert hashlib.sha256(generator.read_bytes()).hexdigest() == (
        "c24ca695116b82823bba5389dd69583c496f44df94ad9585cce3f08892e937db"
    )


def test_o2_header_and_order():
    """Verify data layout and exact day-count inputs."""
    assert {key: _PAYLOAD[key] for key in (
        "schema", "quantlib", "day_count", "compounding", "american_engine", "european_engine",
    )} == {
        "schema": "quimera-quantlib-reference/1", "quantlib": "1.44",
        "day_count": "Actual/365 (Fixed)", "compounding": "continuous",
        "american_engine": "QdFpAmericanEngine/QdFpLegendreTanhSinhScheme(40,100,40,1e-12)/Auto",
        "european_engine": "AnalyticEuropeanEngine",
    }
    assert all(_PAYLOAD[key] for key in ("python", "machine", "system", "evaluation_date"))
    assert len(_PAYLOAD["cross_checks"]) == 3
    assert [row.id for row in _CASES] == [
        f"{group}{i:02d}" for group, total in zip("ABCD", (18, 27, 18, 6), strict=True)
        for i in range(1, total + 1)
    ]
    assert all(row.time_years == row.days / 365 for row in _CASES)


def test_o3_reference_coherence(case):
    """Require the archived controls to remain within their stated bounds."""
    u = max(abs(case.american - case.american_fixed_point_a),
            abs(case.american - case.american_high_precision_scheme))
    assert case.american_uncertainty == u <= 5e-5
    assert abs(case.american_finite_differences - case.american) <= 5e-3
    assert case.american >= case.european - 1e-9
    if case.id.startswith("A"):
        assert abs(case.american - case.european) <= 1e-9


def test_o4_european_bsm(case):
    """Match the analytic European control."""
    price = bsm.price(bsm.BsmInputs(
        OptionKind(case.kind), case.spot, case.strike, case.time_years, case.rate_cont,
        case.sigma, case.dividend_yield,
    ), theta_basis=252).price
    assert abs(price - case.european) <= 1e-11 * max(1., case.european)


def test_o5_tree_price(case):
    """Bound the adjacent tree pair's price error on all cases."""
    bound = 4.5e-4 * case.spot * case.sigma * math.sqrt(case.time_years)
    assert abs(_par(case) - case.american) <= bound + case.american_uncertainty


def test_o6_tree_iv(case, tree_iv):
    """Recover the known volatility outside the near-intrinsic cases."""
    if case.id not in _EDGES:
        assert isinstance(tree_iv, AmericanIvSolution)
        assert abs(tree_iv.sigma - case.sigma) <= 5e-4


def test_o7_fd_price(case):
    """Bound FD price error by the approved mesh-scaled tolerance."""
    sigma, years = case.sigma, case.time_years
    half = max(
        _GRID.width_stdevs * sigma * math.sqrt(years)
        + abs(case.rate_cont - case.dividend_yield - sigma**2 / 2) * years,
        abs(math.log(case.spot / case.strike)) + sigma * math.sqrt(years),
    )
    dx = 2 * half / _GRID.space_nodes
    assert abs(_fd(case) - case.american) <= 0.8 * case.spot * dx**2 + case.american_uncertainty


def test_o8_fd_iv(case, fd_iv):
    """Recover the known volatility within the appropriate regime's bound."""
    if case.id not in _EDGES:
        assert fd_iv.status == "ok" and fd_iv.sigma is not None
        assert abs(fd_iv.sigma - case.sigma) <= (3.5e-4 if case.id.startswith("D") else 1e-4)


def _convergence(pair):
    """Apply the same aggregate refinement metric to each engine."""
    return sum(fine for _, fine in pair) / sum(coarse for coarse, _ in pair)


@pytest.mark.parametrize("engine,limit", [("tree", .15), ("fd", .35)])
def test_o9_convergence(engine, limit):
    """Compare aggregate errors on every third reference case."""
    evaluate = (
        (lambda row: (_par(row), _par(row, 2000))) if engine == "tree"
        else (lambda row: (_fd(row), _fd(row, replace(_GRID, space_nodes=800, time_steps=400))))
    )
    errors = [
        tuple(abs(price - row.american) for price in evaluate(row))
        for row in _CASES[::3]
    ]
    assert len(errors) == 23
    assert _convergence(errors) <= limit


def test_o10_cross_engine_iv(case, tree_iv, fd_iv):
    """Check the offline regression bound, not the live diagnostic warning."""
    if case.id not in _EDGES and case.id[0] in "ABC":
        assert isinstance(tree_iv, AmericanIvSolution)
        assert fd_iv.status == "ok" and fd_iv.sigma is not None
        assert abs(tree_iv.sigma - fd_iv.sigma) <= 5e-4


@pytest.mark.parametrize("row", [row for row in _CASES if row.id in _EDGES], ids=lambda row: row.id)
def test_o11_near_intrinsic(row):
    """Check the near-intrinsic geometry without treating the IV as truth."""
    assert abs(row.american - row.intrinsic) <= row.american_uncertainty


@pytest.mark.parametrize("row", [row for row in _CASES if row.id in _EDGES], ids=lambda row: row.id)
def test_o11b_near_intrinsic_is_refused(row: _Case) -> None:
    """Os dois motores recusam publicar sigma a menos de um tick do piso."""
    tree, fd = _tree_iv(row), _fd_iv(row)
    assert tree.reason == "iv:not_identifiable" and tree.sigma is None
    assert fd.status == "not_identifiable" and fd.sigma is None


def _observation(case):
    """Record errors and keep statuses even in the near-intrinsic cases."""
    tree_iv = _tree_iv(case)
    fd_iv = _fd_iv(case)
    return {
        "id": case.id, "group": case.id[0],
        "tree_price_error": abs(_par(case) - case.american),
        "fd_price_error": abs(_fd(case) - case.american),
        "tree_iv_status": "ok" if isinstance(tree_iv, AmericanIvSolution) else tree_iv.reason,
        "fd_iv_status": fd_iv.status,
        "tree_iv": tree_iv.sigma,
        "fd_iv": fd_iv.sigma,
        "tree_iv_error": None if tree_iv.sigma is None else abs(tree_iv.sigma - case.sigma),
        "fd_iv_error": None if fd_iv.sigma is None else abs(fd_iv.sigma - case.sigma),
    }


def test_o12_report(tmp_path):
    """Write and read back errors for all 69 cases in the four groups."""
    path = tmp_path / "report.json"
    path.write_text(json.dumps([_observation(row) for row in _CASES], allow_nan=False))
    report = json.loads(path.read_bytes())
    assert len(report) == 69
    assert {row["group"] for row in report} == set("ABCD")
    # Revisor: toda linha traz o erro dos dois motores; ausência é nulo, nunca chave faltando.
    keys = {"id", "group", "tree_price_error", "fd_price_error", "tree_iv_status",
            "fd_iv_status", "tree_iv", "fd_iv", "tree_iv_error", "fd_iv_error"}
    assert all(set(row) == keys for row in report)
    for row in report:
        if row["id"] in _EDGES:
            assert row["tree_iv_error"] is None and row["fd_iv_error"] is None
            assert row["tree_iv_status"] == "iv:not_identifiable"
            assert row["fd_iv_status"] == "not_identifiable"
        else:
            assert row["tree_iv_error"] is not None and row["fd_iv_error"] is not None
