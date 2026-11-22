"""Resultado em reais no vencimento comum de opções sobre um único ativo."""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal, localcontext
from fractions import Fraction
from typing import Literal

_ZERO = Decimal(0)
_EXACT = Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX)


class PayoffRefusal(ValueError):
    """Entrada incompatível com um perfil de vencimento."""


def _nonnegative(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise PayoffRefusal(f"{name} exige Decimal finito não negativo")


def _positive_int(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise PayoffRefusal(f"{name} exige inteiro positivo")


@dataclass(frozen=True, slots=True)
class ExpiryLeg:
    """Uma posição de opção com prêmio efetivo por unidade."""
    kind: Literal["CALL", "PUT"]
    side: Literal["BUY", "SELL"]
    strike: Decimal
    quantity: int
    premium: Decimal

    def __post_init__(self) -> None:
        if self.kind not in ("CALL", "PUT") or self.side not in ("BUY", "SELL"):
            raise PayoffRefusal("tipo ou lado de opção inválido")
        _positive_int(self.quantity, "quantidade")
        _nonnegative(self.strike, "strike")
        if self.strike == 0:
            raise PayoffRefusal("strike exige valor positivo")
        _nonnegative(self.premium, "prêmio")

    @property
    def signed_quantity(self) -> int:
        """Quantidade com sinal da posição comprada ou vendida."""
        return self.quantity if self.side == "BUY" else -self.quantity


@dataclass(frozen=True, slots=True)
class ExpiryProfile:
    """Extremos com sinal e extremos finitos dos intervalos de equilíbrio."""
    net_entry: Decimal
    breakevens: tuple[Fraction, ...]
    max_gain: Decimal | None
    max_loss: Decimal | None

    @property
    def gain_unlimited(self) -> bool:
        """O resultado cresce sem limite à direita."""
        return self.max_gain is None

    @property
    def loss_unlimited(self) -> bool:
        """O resultado cai sem limite à direita."""
        return self.max_loss is None


def _structure(legs: Sequence[ExpiryLeg], multiplier: int) -> tuple[ExpiryLeg, ...]:
    _positive_int(multiplier, "multiplicador")
    if not isinstance(legs, Sequence) or not 1 <= len(legs) <= 8:
        raise PayoffRefusal("estrutura exige de uma a oito pernas")
    snapshot = tuple(legs)
    if not all(isinstance(leg, ExpiryLeg) for leg in snapshot):
        raise PayoffRefusal("perna inválida")
    return snapshot


def _results(legs: Sequence[ExpiryLeg], spot: Decimal, multiplier: int) -> tuple[Decimal, ...]:
    parts = []
    for leg in legs:
        distance = spot - leg.strike if leg.kind == "CALL" else leg.strike - spot
        parts.append(leg.signed_quantity * multiplier * (max(_ZERO, distance) - leg.premium))
    return tuple(parts)


def expiry_leg_results(legs: Sequence[ExpiryLeg], spot: Decimal, *,
                       multiplier: int = 1) -> tuple[Decimal, ...]:
    """Resultado por perna, em ordem de entrada e antes dos custos."""
    _nonnegative(spot, "preço final")
    with localcontext(_EXACT):
        return _results(_structure(legs, multiplier), spot, multiplier)


def expiry_result(legs: Sequence[ExpiryLeg], spot: Decimal, *,
                  multiplier: int = 1, costs: Decimal = _ZERO) -> Decimal:
    """Resultado total da estrutura, descontados os custos uma vez."""
    _nonnegative(costs, "custos")
    with localcontext(_EXACT):
        return sum(expiry_leg_results(legs, spot, multiplier=multiplier), _ZERO) - costs


def expiry_profile(legs: Sequence[ExpiryLeg], *, multiplier: int = 1,
                   costs: Decimal = _ZERO) -> ExpiryProfile:
    """Perfil linear por trechos em todo o semieixo de preços não negativos."""
    positions = _structure(legs, multiplier)
    _nonnegative(costs, "custos")
    spots = sorted({_ZERO, *(leg.strike for leg in positions)})
    with localcontext(_EXACT):
        entry = sum((leg.signed_quantity * multiplier * leg.premium for leg in positions), _ZERO)
        values = [sum(_results(positions, s, multiplier), _ZERO) - costs for s in spots]
    tail = multiplier * sum(leg.signed_quantity for leg in positions if leg.kind == "CALL")
    roots: list[Fraction] = []
    for i, (spot, value) in enumerate(zip(spots, values, strict=True)):
        if value == 0:
            # Um trecho inteiro em zero contribui só com suas extremidades finitas.
            starts = i == 0 or values[i - 1] != 0
            ends = values[i + 1] != 0 if i + 1 < len(values) else tail != 0
            if starts or ends:
                roots.append(Fraction(spot))
        elif i and (value < 0 < values[i - 1] or value > 0 > values[i - 1]):
            x, y = Fraction(spots[i - 1]), Fraction(values[i - 1])
            roots.append(x - y * (Fraction(spot) - x) / (Fraction(value) - y))
    if tail and values[-1] != 0:
        last = Fraction(spots[-1])
        crossing = last - Fraction(values[-1]) / tail
        if crossing > last:
            roots.append(crossing)
    return ExpiryProfile(entry, tuple(roots), None if tail > 0 else max(values),
                         None if tail < 0 else min(values))
