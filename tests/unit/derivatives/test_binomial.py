"""Contrato numérico e recusas do núcleo binomial e da parametrização CRR."""

import inspect
import math
import tracemalloc
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from itertools import product
from typing import Any

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing import binomial, bsm
from backend.derivatives.pricing.binomial import (
    BinomialRefusal,
    BinomialRefusalCode,
    TreeParameters,
    crr_parameters,
    crr_price,
    tree_price,
)


def _hand_tree(up: float, down: float, rate: float, steps: int) -> TreeParameters:
    return TreeParameters(up=up, down=down, prob_up=(math.exp(rate) - down) / (up - down),
                          discount=math.exp(-rate), steps=steps)


def test_h1_american_put() -> None:
    """O exercício no nó de baixa do primeiro passo vale mais que a continuação."""
    value = tree_price(kind=OptionKind.PUT, style=ExerciseStyle.AMERICAN, spot=50.0,
                       strike=52.0, tree=_hand_tree(1.2, 0.8, 0.05, 2))
    assert value == pytest.approx(5.089632, abs=5e-5, rel=0)
    assert value == pytest.approx(5.089632474198, abs=1e-9, rel=0)


def test_crr_refuses_inadmissible_probability() -> None:
    """Um passo com carry alto e volatilidade baixa viola a condição de não arbitragem."""
    with pytest.raises(BinomialRefusal) as exc:
        crr_parameters(sigma=0.01, rate_cont=0.5, dividend_yield=0.0, time_years=1.0, steps=1)
    assert exc.value.code is BinomialRefusalCode.PROBABILITY_OUT_OF_RANGE
    assert str(exc.value) == "probability_out_of_range"


CALL, PUT = OptionKind.CALL, OptionKind.PUT
AM, EU = ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN
BASE: dict[str, Any] = dict(kind=PUT, style=AM, spot=100.0, strike=100.0, time_years=1.0,
                            rate_cont=0.10, sigma=0.20, dividend_yield=0.0, steps=200)
TREE = TreeParameters(1.2, 0.8, 0.6, 0.95, 2)


@pytest.mark.parametrize(
    "kind,spot,strike,up,down,rate,steps,european,american",
    [
        (PUT, 50.0, 52.0, 1.2, 0.8, 0.05, 2, 4.192654280604, 5.089632474198),
        (PUT, 50.0, 80.0, 1.2, 0.8, 0.05, 2, 22.386993442877, 30.0),
        (CALL, 100.0, 90.0, 1.1, 0.9, -0.05, 1, 5.385601326158, 10.0),
        (CALL, 100.0, 90.0, 1.1, 0.9, 0.05, 1, 14.389351794936, 14.389351794936),
        (CALL, 50.0, 45.0, 1.2, 0.8, -0.05, 2, 5.824442308122, 6.741456697459),
    ], ids=["H1", "H2", "H3", "H4", "H5"],
)
def test_hand_tree(kind: OptionKind, spot: float, strike: float, up: float, down: float,
                   rate: float, steps: int, european: float, american: float) -> None:
    """Compara os dois estilos à indução manual, incluindo os empates e a raiz."""
    tree = _hand_tree(up, down, rate, steps)
    eu = tree_price(kind=kind, style=EU, spot=spot, strike=strike, tree=tree)
    am = tree_price(kind=kind, style=AM, spot=spot, strike=strike, tree=tree)
    assert abs(eu - european) <= 1e-9
    assert abs(am - american) <= 1e-9
    if strike == 52.0:
        assert abs(eu - 4.192654) <= 5e-5
    if american in (30.0, 10.0):
        assert am == american
    if american == european:
        assert am == eu


@pytest.mark.parametrize("sigma,rate,q,time,steps,expected", [
    (0.2, 0.10, 0.03, 1.0, 200, (1.0142426086996437, 0.9859573946337119,
                                 0.508840646914882, 0.9995001249791693)),
    (0.45, -0.02, 0.0, 0.25, 51, (1.0320078791759375, 0.9689848499979516,
                                  0.49056854288508794, 1.0000980440216873)),
])
def test_crr_formulas(sigma: float, rate: float, q: float, time: float, steps: int,
                      expected: tuple[float, ...]) -> None:
    """Confere as quatro fórmulas por passo, a reciprocidade e o prazo da árvore."""
    tree = crr_parameters(sigma=sigma, rate_cont=rate, dividend_yield=q,
                          time_years=time, steps=steps)
    assert (tree.up, tree.down, tree.prob_up, tree.discount) == pytest.approx(
        expected, rel=1e-14, abs=0)
    assert tree.down == 1.0 / tree.up
    assert tree.steps == steps


# Mesma ordem do cartão. A última coluna é o coeficiente dd fixado antes do GREEN.
_CASES = [
    (CALL, 100.0, 1.0, .10, .20, .0, 2.08821),
    (PUT, 100.0, 1.0, .10, .20, .0, 2.08821),
    (CALL, 90.0, .5, .05, .30, .0, 1.73123),
    (PUT, 110.0, .5, .05, .30, .0, 2.31064),
    (CALL, 110.0, .25, .12, .25, .0, 1.54177),
    (PUT, 90.0, .25, .12, .25, .0, 0.75104),
    (CALL, 100.0, 2.0, .08, .15, .03, 2.0676),
    (PUT, 100.0, 2.0, .08, .15, .03, 2.0676),
    (CALL, 120.0, 1.0, .10, .40, .0, 4.87121),
    (PUT, 80.0, 1.0, .10, .40, .0, 2.60857),
    (CALL, 80.0, 1.0, .14, .20, .05, 0.609434),
    (PUT, 120.0, 1.0, .14, .20, .05, 3.12159),
    (CALL, 100.0, 21/252, .10, .30, .0, 0.863823),
    (PUT, 100.0, 21/252, .10, .30, .0, 0.863823),
    (CALL, 105.0, .75, -.01, .25, .0, 2.17055),
    (PUT, 95.0, .75, -.01, .25, .0, 2.11796),
    (CALL, 100.0, 1.5, .02, .50, .02, 5.83235),
    (PUT, 100.0, 1.5, .02, .50, .02, 5.83235),
    (CALL, 95.0, 5/252, .15, .10, .0, 0.00040489),
    (PUT, 102.0, 5/252, .15, .10, .0, 0.13198),
    (CALL, 100.0, 1.0, .0, .20, .0, 1.99138),
    (PUT, 100.0, 1.0, .0, .20, .0, 1.99138),
    (CALL, 130.0, 1.0, .10, .20, .0, 3.5057),
    (PUT, 70.0, 1.0, .10, .20, .0, 0.200291),
]


@pytest.mark.parametrize("case", [0, 7, 14])
@pytest.mark.parametrize("style", [EU, AM])
def test_composition(case: int, style: ExerciseStyle) -> None:
    """A entrada composta coincide exatamente com as duas chamadas públicas."""
    kind, strike, time, rate, sigma, q, _ = _CASES[case]
    tree = crr_parameters(sigma=sigma, rate_cont=rate, dividend_yield=q, time_years=time, steps=201)
    result = crr_price(kind=kind, style=style, spot=100.0, strike=strike, time_years=time,
                       rate_cont=rate, sigma=sigma, dividend_yield=q, steps=201)
    assert result == tree_price(kind=kind, style=style, spot=100.0, strike=strike, tree=tree)


def test_european_bsm_and_parity() -> None:
    """Mede os erros individuais e agregados com pares par/ímpar e paridade em cada árvore."""
    coarse = fine = 0.0
    for case, (kind, strike, time, rate, sigma, q, dd) in enumerate(_CASES, start=1):
        inputs = bsm.BsmInputs(kind=kind, spot=100.0, strike=strike, time_years=time,
                               rate_cont=rate, sigma=sigma, dividend_yield=q)
        reference = bsm.price(inputs, theta_basis=252).price
        forward_gap = 100.0 * math.exp(-q * time) - strike * math.exp(-rate * time)
        errors = {}
        for steps in (200, 201, 1000, 1001):
            tree = crr_parameters(sigma=sigma, rate_cont=rate, dividend_yield=q,
                                  time_years=time, steps=steps)
            call = tree_price(kind=CALL, style=EU, spot=100.0, strike=strike, tree=tree)
            put = tree_price(kind=PUT, style=EU, spot=100.0, strike=strike, tree=tree)
            error = (call if kind is CALL else put) - reference
            assert abs(error) <= (0.15 if steps < 1000 else 0.03), (case, steps, error)
            assert abs(error) <= 1.25 * dd / steps + 1e-6, (case, steps, error, dd)
            assert abs(call - put - forward_gap) <= 1e-9, (case, steps, call, put)
            errors[steps] = error
        coarse += abs((errors[200] + errors[201]) / 2)
        fine += abs((errors[1000] + errors[1001]) / 2)
    assert fine <= 0.30 * coarse


@pytest.mark.parametrize("kind,strike,sigma,time,rate,q,steps", product(
    (CALL, PUT), (70.0, 100.0, 130.0), (.15, .45), (.1, 1.0), (-.02, .0, .12),
    (.0, .06), (50, 51, 200),
))
def test_grid(kind: OptionKind, strike: float, sigma: float, time: float, rate: float,
              q: float, steps: int) -> None:
    """Exercício e continuação obedecem às desigualdades exatas e às regiões sem prêmio."""
    tree = crr_parameters(sigma=sigma, rate_cont=rate, dividend_yield=q, time_years=time,
                          steps=steps)
    am = tree_price(kind=kind, style=AM, spot=100.0, strike=strike, tree=tree)
    eu = tree_price(kind=kind, style=EU, spot=100.0, strike=strike, tree=tree)
    assert am >= eu
    assert am >= max(0.0, 100.0 - strike if kind is CALL else strike - 100.0)
    if (kind is CALL and q == 0 and rate >= 0) or (kind is PUT and rate <= 0 and q >= rate):
        assert abs(am - eu) <= 1e-11 * max(1.0, eu)


def test_negative_rate_call_premium() -> None:
    """Taxa negativa admite exercício antecipado da call sem rendimento."""
    args = BASE | dict(kind=CALL, strike=90.0, rate_cont=-0.05)
    assert crr_price(**args) - crr_price(**(args | dict(style=EU))) > 0.5


@pytest.mark.parametrize("updates,code", [
    *[({"spot": value}, "invalid_input_type") for value in (Decimal("100"), 100, True)],
    ({"sigma": "0.2"}, "invalid_input_type"), ({"rate_cont": None}, "invalid_input_type"),
    ({"kind": "PUT"}, "invalid_input_type"), ({"style": "AMERICAN"}, "invalid_input_type"),
    ({"style": ExerciseStyle.UNKNOWN}, "unknown_exercise_style"),
    *[({key: value}, "non_finite_input") for key, value in (
        ("spot", math.nan), ("rate_cont", math.inf), ("sigma", -math.inf))],
    *[({"steps": value}, "invalid_steps") for value in (0, -1, 5001, True, 200.0, "200")],
    *[({key: value}, "input_out_of_domain") for key, value in (
        ("spot", 0.0), ("strike", -1.0), ("sigma", -0.1), ("time_years", -1.0),
        ("dividend_yield", -0.01))],
    ({"sigma": 0.0}, "zero_volatility"),
    *[({"sigma": .01, "rate_cont": r, "steps": n}, "probability_out_of_range")
      for r, n in ((.5, 1), (-.5, 1), (.5, 2400))],
    ({"sigma": 5.0, "time_years": 100.0, "steps": 5000}, "tree_not_representable"),
    ({"sigma": 800.0, "steps": 1}, "tree_not_representable"),
    ({"time_years": 1e-40, "steps": 1}, "tree_not_representable"),
    ({"spot": Decimal("1"), "style": ExerciseStyle.UNKNOWN}, "invalid_input_type"),
    ({"style": ExerciseStyle.UNKNOWN, "spot": math.nan}, "unknown_exercise_style"),
    ({"spot": math.nan, "steps": 0}, "non_finite_input"),
    ({"steps": 0, "spot": -1.0}, "invalid_steps"),
    ({"spot": -1.0, "sigma": 0.0}, "input_out_of_domain"),
    ({"time_years": 0.0, "steps": 0}, "invalid_steps"),
    ({"time_years": 0.0, "sigma": -0.1}, "input_out_of_domain"),
    ({"sigma": 0.0, "rate_cont": .5}, "zero_volatility"),
])
def test_price_refusals(updates: dict[str, Any], code: str) -> None:
    """Prende o código, a precedência e a mensagem em cada combinação de entrada."""
    with pytest.raises(BinomialRefusal) as exc:
        crr_price(**(BASE | updates))
    assert exc.value.code is BinomialRefusalCode(code)
    assert str(exc.value) == code


@pytest.mark.parametrize("updates,code", [
    *[({"prob_up": p}, "probability_out_of_range") for p in (0.0, 1.0, -.1, 1.2)],
    *[({key: val}, "input_out_of_domain") for key, val in (
        ("up", .8), ("down", 0.0), ("discount", 0.0))],
    ({"up": .8, "prob_up": 2.0}, "input_out_of_domain"),
    ({"up": 1}, "invalid_input_type"), ({"steps": 0}, "invalid_steps"),
    ({"down": math.nan}, "non_finite_input"),
    ({"up": 1e154}, "tree_not_representable"),  # maior ativo transborda na multiplicação
    ({"discount": 1e308}, "tree_not_representable"),  # continuação não finita
])
def test_tree_refusals(updates: dict[str, Any], code: str) -> None:
    """A árvore fornecida pelo chamador passa pela validação do núcleo."""
    with pytest.raises(BinomialRefusal) as exc:
        tree_price(kind=PUT, style=AM, spot=50.0, strike=52.0, tree=replace(TREE, **updates))
    assert exc.value.code is BinomialRefusalCode(code)
    assert str(exc.value) == code


@pytest.mark.parametrize("updates,code", [
    ({"spot": 0.0}, "input_out_of_domain"), ({"tree": {}}, "invalid_input_type"),
    ({"tree": {}, "style": ExerciseStyle.UNKNOWN}, "invalid_input_type"),
    ({"spot": 50, "style": ExerciseStyle.UNKNOWN}, "invalid_input_type"),
    ({"kind": "PUT"}, "invalid_input_type"), ({"style": "AMERICAN"}, "invalid_input_type"),
    ({"spot": math.nan, "style": ExerciseStyle.UNKNOWN}, "unknown_exercise_style"),
])
def test_tree_input_refusals(updates: dict[str, Any], code: str) -> None:
    """Confere tipo e precedência também na entrada direta do núcleo."""
    args: dict[str, Any] = dict(kind=PUT, style=AM, spot=50.0, strike=52.0, tree=TREE)
    with pytest.raises(BinomialRefusal) as exc:
        tree_price(**(args | updates))
    assert exc.value.code is BinomialRefusalCode(code)
    assert str(exc.value) == code


@pytest.mark.parametrize("updates,code", [
    ({"time_years": 0.0}, "tree_not_representable"),
    ({"time_years": 0.0, "sigma": 0.0}, "tree_not_representable"),
    ({"sigma": .01, "time_years": 1e5, "rate_cont": 1e308, "steps": 1}, "tree_not_representable"),
    ({"rate_cont": 0, "steps": 0}, "invalid_input_type"),
    ({"sigma": math.nan, "steps": 0}, "non_finite_input"),
    ({"steps": False, "time_years": -1.0}, "invalid_steps"),
    ({"time_years": -1.0, "sigma": 0.0}, "input_out_of_domain"),
    ({"sigma": 0.0}, "zero_volatility"),
])
def test_parameter_refusals(updates: dict[str, Any], code: str) -> None:
    """A parametrização pública avalia tipos e domínio antes de construir a árvore."""
    args = {key: BASE[key] for key in ("rate_cont", "dividend_yield", "sigma",
                                       "time_years", "steps")}
    with pytest.raises(BinomialRefusal) as exc:
        crr_parameters(**(args | updates))
    assert exc.value.code is BinomialRefusalCode(code)
    assert str(exc.value) == code


@pytest.mark.parametrize("updates", [
    {"steps": 1}, {"steps": 5000}, {"sigma": .01, "rate_cont": .5, "steps": 2600},
])
def test_valid_steps(updates: dict[str, Any]) -> None:
    """Limites inclusivos de passos e caso admissível longe da fronteira de p."""
    assert math.isfinite(crr_price(**(BASE | updates)))


def test_discount_above_one() -> None:
    """Taxa negativa admite fator de desconto maior que um."""
    assert math.isfinite(tree_price(kind=PUT, style=AM, spot=50.0, strike=52.0,
                                    tree=replace(TREE, discount=1.05)))


@pytest.mark.parametrize("kind,strike,expected", [
    (CALL, 90.0, 10.0), (CALL, 110.0, 0.0), (PUT, 90.0, 0.0), (PUT, 110.0, 10.0),
    (PUT, 100.0, 0.0),
])
@pytest.mark.parametrize("style", [AM, EU])
@pytest.mark.parametrize("sigma", [0.0, 0.2])
def test_expiry(kind: OptionKind, strike: float, expected: float,
                style: ExerciseStyle, sigma: float) -> None:
    """No vencimento vale o intrínseco exato, inclusive com volatilidade zero."""
    assert crr_price(**(BASE | dict(kind=kind, style=style, strike=strike, sigma=sigma,
                                    time_years=0.0))) == expected


def test_determinism() -> None:
    """Chamadas repetidas preservam preço, tipo e estado do módulo."""
    before = {key: repr(value) for key, value in vars(binomial).items()}
    first = crr_price(**BASE)
    assert type(first) is float
    assert first == crr_price(**BASE)
    assert before == {key: repr(value) for key, value in vars(binomial).items()}


def test_linear_memory() -> None:
    """Uma americana de mil passos cabe em menos de 1 MiB de alocações Python."""
    tracemalloc.start()
    try:
        crr_price(**(BASE | {"steps": 1000}))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024, peak


def test_public_signatures() -> None:
    """As três entradas exigem todos os parâmetros por nome."""
    for function in (tree_price, crr_price, crr_parameters):
        for param in inspect.signature(function).parameters.values():
            assert param.kind is inspect.Parameter.KEYWORD_ONLY
            assert param.default is inspect.Parameter.empty


def test_tree_value_object() -> None:
    """Os parâmetros têm slots e não permitem alteração após a construção."""
    assert not hasattr(TREE, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(TREE, "steps", 5)


def test_tiny_down_factor() -> None:
    """O ativo após duas baixas ainda cabe em float quando down ao quadrado já zerou."""
    tree = TreeParameters(up=1.0, down=1e-200, prob_up=.5, discount=1.0, steps=2)
    value = tree_price(kind=PUT, style=EU, spot=1e300, strike=2e-100, tree=tree)
    assert value == pytest.approx(2.5e-101, rel=1e-14, abs=0)


# Testes acrescentados na revisão independente (Claude). Cada um prende um mutante que
# sobrevivia à suíte do autor; a produção já estava correta em todos eles.


@pytest.mark.parametrize("updates", [
    {"strike": 0.0, "time_years": 0.0},
    {"spot": 0.0, "time_years": 0.0},
    {"dividend_yield": -0.01, "time_years": 0.0},
])
def test_price_domain_holds_at_expiry(updates: dict[str, Any]) -> None:
    """No vencimento, zero exato em spot ou strike e rendimento negativo não viram intrínseco."""
    with pytest.raises(BinomialRefusal) as exc:
        crr_price(**(BASE | updates))
    assert exc.value.code is BinomialRefusalCode.INPUT_OUT_OF_DOMAIN


def test_tree_refuses_zero_strike() -> None:
    """O núcleo recusa strike exatamente zero, não só negativo."""
    with pytest.raises(BinomialRefusal) as exc:
        tree_price(kind=PUT, style=AM, spot=50.0, strike=0.0, tree=TREE)
    assert exc.value.code is BinomialRefusalCode.INPUT_OUT_OF_DOMAIN


@pytest.mark.parametrize("updates,code", [
    ({"sigma": -0.1}, "input_out_of_domain"),
    ({"dividend_yield": -0.01}, "input_out_of_domain"),
    # exp(-1e5) arredonda para zero: a árvore sairia com desconto nulo
    ({"rate_cont": 1e5, "dividend_yield": 1e5, "steps": 1}, "tree_not_representable"),
    # o expoente vai a infinito sem OverflowError; up deixa de ser finito
    ({"sigma": 1.7e308, "time_years": 4.0, "steps": 1}, "tree_not_representable"),
])
def test_parameters_direct_domain(updates: dict[str, Any], code: str) -> None:
    """Chamada direta de crr_parameters nunca devolve árvore invertida ou com desconto nulo."""
    args = {key: BASE[key] for key in ("rate_cont", "dividend_yield", "sigma",
                                       "time_years", "steps")}
    with pytest.raises(BinomialRefusal) as exc:
        crr_parameters(**(args | updates))
    assert exc.value.code is BinomialRefusalCode(code)


class _LooseTree(TreeParameters):
    """Subclasse que um chamador poderia usar para trocar o comportamento dos campos."""

    __slots__ = ()


def test_tree_subclass_is_refused() -> None:
    """A árvore tem de ser TreeParameters exato, como os números têm de ser float exato."""
    with pytest.raises(BinomialRefusal) as exc:
        tree_price(kind=PUT, style=AM, spot=50.0, strike=52.0,
                   tree=_LooseTree(1.2, 0.8, 0.6, 0.95, 2))
    assert exc.value.code is BinomialRefusalCode.INVALID_INPUT_TYPE
