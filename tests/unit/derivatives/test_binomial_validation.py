"""Referência independente da árvore finita e invariantes do Marco 2A."""

import hashlib
import json
import math
from collections import Counter
from decimal import Decimal
from itertools import product
from pathlib import Path
from runpy import run_path
from typing import TypedDict

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.binomial import (
    BinomialRefusal,
    BinomialRefusalCode,
    TreeParameters,
    crr_parameters,
    crr_price,
    tree_price,
)


class ReferenceCase(TypedDict):
    """Entradas em repr de float e resultados decimais publicados no JSON."""

    case_id: str
    kind: str
    S: str
    K: str
    r_cont: str
    q: str
    sigma: str
    T_years: str
    steps: int
    up: str
    prob_up: str
    discount: str
    european_price: str
    american_price: str


REFERENCE = (Path(__file__).resolve().parents[2] / "fixtures" / "derivatives" / "reference"
             / "crr_american_reference.json")
SHA256 = "04fbaa7c5bd00e2bfabd52176be0a54a7ba8ddfc4d0892e50d74fec17201d135"
GENERATOR_SHA256 = "4d8f7eef3151a036cd4d4cd5f8dffaeb5e0fde3f1599aa5d2f9cab6f30d922a0"
DOCUMENT = json.loads(REFERENCE.read_bytes())
CASES: list[ReferenceCase] = DOCUMENT["cases"]
CASE_IDS = [case["case_id"] for case in CASES]
CALL, PUT = OptionKind.CALL, OptionKind.PUT
AM, EU = ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN


def test_reference_digest() -> None:
    """T1. Fixa os bytes do JSON e a linha inteira do arquivo de soma."""
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == SHA256
    checksum = REFERENCE.with_suffix(".sha256").read_bytes()
    assert checksum == f"{SHA256}  crr_american_reference.json\n".encode("ascii")


def test_generator_digest() -> None:
    """Fixa os bytes do gerador: T2 não exercita as conferências internas dele."""
    generator = REFERENCE.with_name("crr_reference_generator.py")
    assert hashlib.sha256(generator.read_bytes()).hexdigest() == GENERATOR_SHA256


def test_reference_regenerates() -> None:
    """T2. A aritmética independente regenera inclusive a serialização UTF-8."""
    generator = run_path(str(REFERENCE.with_name("crr_reference_generator.py")))
    assert generator["build_document"]().encode("utf-8") == REFERENCE.read_bytes()


def test_reference_cases() -> None:
    """T3. Confere entradas canônicas, tipos e distribuição dos prêmios de exercício."""
    assert len(CASES) == DOCUMENT["metadata"]["casos"] == len(set(CASE_IDS)) == 42
    assert Counter(case["kind"] for case in CASES) == {"call": 20, "put": 22}
    premium: Counter[str] = Counter()
    equal = set()
    for case in CASES:
        for value in (case["S"], case["K"], case["r_cont"], case["q"], case["sigma"],
                      case["T_years"]):
            assert repr(float(value)) == value, case["case_id"]
        american = Decimal(case["american_price"])
        european = Decimal(case["european_price"])
        if american > european:
            premium[case["kind"]] += 1
        elif american == european:
            equal.add(case["case_id"])
    assert premium.total() == 35
    assert premium["call"] == 16
    assert equal == {
        "crr_14_call_yield", "crr_29_negative_rate", "crr_30_negative_rate",
        "crr_31_no_premium", "crr_32_no_premium", "crr_33_no_premium", "crr_39_small_trees",
    }


def _assert_reference(actual: float, published: str, tolerance: str) -> None:
    reference = Decimal(published)
    assert abs(Decimal(actual) - reference) <= Decimal(tolerance) * max(Decimal(1), abs(reference))


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_reference_prices(case: ReferenceCase) -> None:
    """T4. Compara cada estilo ao preço da árvore finita sem arredondar a referência."""
    for style, published in ((AM, case["american_price"]), (EU, case["european_price"])):
        price = crr_price(kind=OptionKind(case["kind"].upper()), style=style,
                          spot=float(case["S"]), strike=float(case["K"]),
                          time_years=float(case["T_years"]), rate_cont=float(case["r_cont"]),
                          sigma=float(case["sigma"]), dividend_yield=float(case["q"]),
                          steps=case["steps"])
        _assert_reference(price, published, "1e-11")


def _reference_tree(case: ReferenceCase) -> TreeParameters:
    return crr_parameters(sigma=float(case["sigma"]), rate_cont=float(case["r_cont"]),
                          dividend_yield=float(case["q"]), time_years=float(case["T_years"]),
                          steps=case["steps"])


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_reference_parameters(case: ReferenceCase) -> None:
    """T5. Confere movimento, probabilidade e desconto da mesma árvore publicada."""
    tree = _reference_tree(case)
    _assert_reference(tree.up, case["up"], "1e-14")
    _assert_reference(tree.prob_up, case["prob_up"], "1e-11")
    _assert_reference(tree.discount, case["discount"], "1e-14")


def test_hull_anchor() -> None:
    """T6. Reproduz as casas publicadas para a árvore de cinco passos de Hull."""
    case = next(case for case in CASES if case["case_id"] == "crr_01_hull")
    tree = _reference_tree(case)
    assert tree.steps == 5
    assert f"{tree.up:.4f}" == "1.1224"
    assert f"{tree.down:.4f}" == "0.8909"
    assert f"{tree.prob_up:.4f}" == "0.5073"
    assert f"{tree.prob_up * (tree.up - tree.down) + tree.down:.4f}" == "1.0084"
    assert f"{float(case['T_years']) / 5:.5f}" == "0.08333"
    assert f"{50.0 * tree.down**3:.2f}" == "35.36"


def _prices(kind: OptionKind, spot: float, strike: float, tree: TreeParameters
            ) -> tuple[float, float]:
    american = tree_price(kind=kind, style=AM, spot=spot, strike=strike, tree=tree)
    european = tree_price(kind=kind, style=EU, spot=spot, strike=strike, tree=tree)
    return american, european


def _tolerance(price: float) -> float:
    return 1e-11 * max(1.0, price)


def test_grid_invariants() -> None:
    """T7. Decide admissibilidade pela fronteira CRR e conta os pontos de cada invariante."""
    counts: Counter[str] = Counter()
    spot = 100.0
    grid = product((CALL, PUT), (60.0, 85.0, 100.0, 115.0, 140.0), (0.011, 0.12, 0.3, 0.7),
                   (0.05, 0.5, 2.0), (-0.03, 0.0, 0.05, 0.13), (0.0, 0.04, 0.10), (50, 51))
    for point in grid:
        kind, strike, sigma, time, rate, q, steps = point
        counts["total"] += 1
        admissible = abs(rate - q) * math.sqrt(time / steps) < sigma
        try:
            tree = crr_parameters(sigma=sigma, rate_cont=rate, dividend_yield=q,
                                  time_years=time, steps=steps)
        except BinomialRefusal as refusal:
            assert not admissible, point
            assert refusal.code is BinomialRefusalCode.PROBABILITY_OUT_OF_RANGE, point
            counts["refused"] += 1
            continue
        assert admissible, point
        am, eu = _prices(kind, spot, strike, tree)
        assert math.isfinite(am) and math.isfinite(eu), ("G1", point)
        assert am >= eu >= 0.0, ("G1", point)
        intrinsic = max(0.0, spot - strike if kind is CALL else strike - spot)
        assert am >= intrinsic, ("G2", point)
        counts["priced"] += 1
        if kind is CALL and q == 0 and rate >= 0:
            assert abs(am - eu) <= _tolerance(eu), ("G3", point)
            counts["G3"] += 1
        if kind is PUT and rate <= 0:
            assert abs(am - eu) <= _tolerance(eu), ("G4", point)
            counts["G4"] += 1
        if kind is CALL and q == 0 and rate < 0 and strike <= 85 and sigma >= 0.12:
            assert am - eu > 0.01, ("G5", point)
            counts["G5"] += 1
        if rate >= 0:
            symmetric = crr_parameters(sigma=sigma, rate_cont=q, dividend_yield=rate,
                                       time_years=time, steps=steps)
            dual_am, dual_eu = _prices(PUT if kind is CALL else CALL, strike, spot, symmetric)
            assert abs(am - dual_am) <= _tolerance(am), ("G6", point)
            assert abs(eu - dual_eu) <= _tolerance(eu), ("G6", point)
            counts["G6"] += 1
    assert counts == {"total": 2880, "priced": 2740, "refused": 140,
                      "G3": 340, "G4": 680, "G5": 36, "G6": 2080}
