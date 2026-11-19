"""Indução retroativa em árvore binomial recombinante."""

from dataclasses import dataclass

from backend.derivatives.domain.models import ExerciseStyle, OptionKind


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
