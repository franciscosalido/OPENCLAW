"""Indução retroativa em árvore binomial recombinante."""

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


def tree_price(*, kind: OptionKind, style: ExerciseStyle, spot: float, strike: float,
               tree: TreeParameters) -> float:
    """Desconta os payoffs do vencimento até a raiz."""
    sign = 1.0 if kind is OptionKind.CALL else -1.0
    assets_up = [spot * tree.up**j for j in range(tree.steps + 1)]
    down = [tree.down**k for k in range(tree.steps + 1)]
    values = [max(0.0, sign * (asset * down[tree.steps - j] - strike))
              for j, asset in enumerate(assets_up)]
    for level in reversed(range(tree.steps)):
        for j in range(level + 1):
            values[j] = tree.discount * (tree.prob_up * values[j + 1]
                                         + (1.0 - tree.prob_up) * values[j])
    return values[0]


def crr_parameters(*, sigma: float, rate_cont: float, dividend_yield: float, time_years: float,
                   steps: int) -> TreeParameters:
    """Monta os parâmetros por passo de Cox, Ross e Rubinstein."""
    dt = time_years / steps
    up = math.exp(sigma * math.sqrt(dt))
    down = 1.0 / up
    growth = math.exp((rate_cont - dividend_yield) * dt)
    prob_up = (growth - down) / (up - down)
    return TreeParameters(up, down, prob_up, math.exp(-rate_cont * dt), steps)
