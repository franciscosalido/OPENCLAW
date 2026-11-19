"""Precificação binomial isolada e parametrização de Cox, Ross e Rubinstein."""

import math
from dataclasses import dataclass
from enum import StrEnum

from backend.derivatives.domain.models import ExerciseStyle, OptionKind


class BinomialRefusalCode(StrEnum):
    """Identificadores estáveis das recusas da árvore."""

    INVALID_INPUT_TYPE = "invalid_input_type"
    UNKNOWN_EXERCISE_STYLE = "unknown_exercise_style"
    NON_FINITE_INPUT = "non_finite_input"
    INVALID_STEPS = "invalid_steps"
    INPUT_OUT_OF_DOMAIN = "input_out_of_domain"
    ZERO_VOLATILITY = "zero_volatility"
    PROBABILITY_OUT_OF_RANGE = "probability_out_of_range"
    TREE_NOT_REPRESENTABLE = "tree_not_representable"


class BinomialRefusal(Exception):
    """Recusa tipada cuja mensagem contém somente o código."""

    def __init__(self, code: BinomialRefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class TreeParameters:
    """Movimentos, probabilidade e desconto por passo de uma árvore recombinante."""

    up: float
    down: float
    prob_up: float
    discount: float
    steps: int


def _check_option_types(kind: OptionKind, style: ExerciseStyle) -> None:
    if type(kind) is not OptionKind or type(style) is not ExerciseStyle:
        raise BinomialRefusal(BinomialRefusalCode.INVALID_INPUT_TYPE)


def _check_inputs(numbers: tuple[float, ...], steps: int, style: ExerciseStyle | None) -> None:
    if any(type(value) is not float for value in numbers):
        raise BinomialRefusal(BinomialRefusalCode.INVALID_INPUT_TYPE)
    if style is ExerciseStyle.UNKNOWN:
        raise BinomialRefusal(BinomialRefusalCode.UNKNOWN_EXERCISE_STYLE)
    if not all(math.isfinite(value) for value in numbers):
        raise BinomialRefusal(BinomialRefusalCode.NON_FINITE_INPUT)
    if type(steps) is not int or not 1 <= steps <= 5000:
        raise BinomialRefusal(BinomialRefusalCode.INVALID_STEPS)


def _check_probability(prob_up: float) -> None:
    if not 0.0 < prob_up < 1.0:
        raise BinomialRefusal(BinomialRefusalCode.PROBABILITY_OUT_OF_RANGE)


def tree_price(*, kind: OptionKind, style: ExerciseStyle, spot: float, strike: float,
               tree: TreeParameters) -> float:
    """Desconta os payoffs e compara o exercício americano em cada nó até a raiz."""
    _check_option_types(kind, style)
    if type(tree) is not TreeParameters:
        raise BinomialRefusal(BinomialRefusalCode.INVALID_INPUT_TYPE)
    _check_inputs((spot, strike, tree.up, tree.down, tree.prob_up, tree.discount),
                  tree.steps, style)
    if spot <= 0 or strike <= 0 or tree.down <= 0 or tree.up <= tree.down or tree.discount <= 0:
        raise BinomialRefusal(BinomialRefusalCode.INPUT_OUT_OF_DOMAIN)
    _check_probability(tree.prob_up)
    try:
        if not math.isfinite(spot * tree.up**tree.steps):
            raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
    except OverflowError:
        raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE) from None

    sign = 1.0 if kind is OptionKind.CALL else -1.0
    prob_up = tree.prob_up
    prob_down = 1.0 - prob_up
    american = style is ExerciseStyle.AMERICAN
    peaks = [spot]
    for _ in range(tree.steps):
        peaks.append(peaks[-1] * tree.up)

    if not math.isfinite(peaks[-1]):
        raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)

    # Uma coluna reúne os nós com o mesmo número de altas. Multiplicar o ativo
    # por down a cada baixa preserva nós cujo fator down**k sozinho iria a zero.
    assets = [0.0] * (tree.steps + 1)
    values = assets.copy()
    for rises in range(tree.steps, -1, -1):
        depth = tree.steps - rises
        assets[0] = spot if rises == 0 else peaks[rises]
        for k in range(depth):
            assets[k + 1] = assets[k] * tree.down
        values[depth] = max(0.0, sign * (assets[depth] - strike))
        for k in reversed(range(depth)):
            # O filho de alta está na coluna anterior; o de baixa já está nesta coluna.
            continuation = tree.discount * (prob_up * values[k] + prob_down * values[k + 1])
            if american:
                continuation = max(continuation, sign * (assets[k] - strike))
            values[k] = continuation
    if not math.isfinite(values[0]):
        raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
    return values[0]


def crr_parameters(*, sigma: float, rate_cont: float, dividend_yield: float, time_years: float,
                   steps: int) -> TreeParameters:
    """Monta os parâmetros por passo de CRR ou recusa uma árvore inadmissível."""
    _check_inputs((sigma, rate_cont, dividend_yield, time_years), steps, None)
    if min(sigma, dividend_yield, time_years) < 0:
        raise BinomialRefusal(BinomialRefusalCode.INPUT_OUT_OF_DOMAIN)
    if sigma == 0.0 and time_years > 0.0:
        raise BinomialRefusal(BinomialRefusalCode.ZERO_VOLATILITY)
    dt = time_years / steps
    try:
        up = math.exp(sigma * math.sqrt(dt))
        if not math.isfinite(up):
            raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
        down = 1.0 / up
        if up == down:
            raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
        growth = math.exp((rate_cont - dividend_yield) * dt)
        if not math.isfinite(growth):
            raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
        prob_up = (growth - down) / (up - down)
        _check_probability(prob_up)
        discount = math.exp(-rate_cont * dt)
    except OverflowError:
        raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE) from None
    if discount == 0.0 or not math.isfinite(discount):
        raise BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
    return TreeParameters(up, down, prob_up, discount, steps)


def crr_price(*, kind: OptionKind, style: ExerciseStyle, spot: float, strike: float,
              time_years: float, rate_cont: float, sigma: float, dividend_yield: float,
              steps: int) -> float:
    """Devolve o intrínseco no vencimento ou o preço por indução na árvore CRR."""
    _check_option_types(kind, style)
    _check_inputs((spot, strike, time_years, rate_cont, sigma, dividend_yield), steps, style)
    if spot <= 0 or strike <= 0 or min(sigma, dividend_yield, time_years) < 0:
        raise BinomialRefusal(BinomialRefusalCode.INPUT_OUT_OF_DOMAIN)
    if time_years == 0.0:
        return max(0.0, spot - strike if kind is OptionKind.CALL else strike - spot)
    tree = crr_parameters(sigma=sigma, rate_cont=rate_cont, dividend_yield=dividend_yield,
                          time_years=time_years, steps=steps)
    return tree_price(kind=kind, style=style, spot=spot, strike=strike, tree=tree)
