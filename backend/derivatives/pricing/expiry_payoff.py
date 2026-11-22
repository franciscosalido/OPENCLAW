"""Resultado em reais no vencimento comum de opções sobre um único ativo."""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation
from fractions import Fraction
from itertools import islice
from typing import Literal

_ZERO = Decimal(0)
_Position = tuple[bool, int, int, int]  # call, strike, quantidade assinada e escalada, prêmio


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



def _units(value: Decimal, exponent: int) -> int:
    if not value:
        return 0
    sign, digits, power = value.as_tuple()
    factor: int = 10 ** (int(power) - exponent)
    return int(Decimal((sign, digits, 0))) * factor


def _money(units: int, exponent: int) -> Decimal:
    sign, digits, _ = Decimal(units).as_tuple()
    try:
        return Decimal((sign, digits, exponent), context=Context(traps=[InvalidOperation]))
    except InvalidOperation as exc:
        raise PayoffRefusal("resultado fora da representação Decimal") from exc


def _structure(legs: Sequence[ExpiryLeg], multiplier: int,
               *amounts: Decimal) -> tuple[tuple[_Position, ...], int]:
    _positive_int(multiplier, "multiplicador")
    snapshot = tuple(islice(legs, 9)) if isinstance(legs, Sequence) else ()
    if not 1 <= len(snapshot) <= 8 or not all(isinstance(leg, ExpiryLeg) for leg in snapshot):
        raise PayoffRefusal("estrutura exige de uma a oito pernas válidas")
    for value in amounts:
        _nonnegative(value, "preço final ou custos")
    prices = (*amounts, *(v for leg in snapshot for v in (leg.strike, leg.premium)))
    exponent = min(int(v.as_tuple().exponent) for v in prices if v)
    return tuple((leg.kind == "CALL", _units(leg.strike, exponent),
                  multiplier * (leg.quantity if leg.side == "BUY" else -leg.quantity),
                  _units(leg.premium, exponent)) for leg in snapshot), exponent


def _results(positions: tuple[_Position, ...], spot: int) -> tuple[int, ...]:
    return tuple(qty * (max(0, spot - strike if call else strike - spot) - premium)
                 for call, strike, qty, premium in positions)


def expiry_leg_results(legs: Sequence[ExpiryLeg], spot: Decimal, *,
                       multiplier: int = 1) -> tuple[Decimal, ...]:
    """Resultado por perna, em ordem de entrada e antes dos custos."""
    positions, exp = _structure(legs, multiplier, spot)
    return tuple(_money(n, exp) for n in _results(positions, _units(spot, exp)))


def expiry_result(legs: Sequence[ExpiryLeg], spot: Decimal, *,
                  multiplier: int = 1, costs: Decimal = _ZERO) -> Decimal:
    """Resultado total da estrutura, descontados os custos uma vez."""
    positions, exp = _structure(legs, multiplier, spot, costs)
    return _money(sum(_results(positions, _units(spot, exp))) - _units(costs, exp), exp)


def expiry_profile(legs: Sequence[ExpiryLeg], *, multiplier: int = 1,
                   costs: Decimal = _ZERO) -> ExpiryProfile:
    """Perfil linear por trechos em todo o semieixo de preços não negativos."""
    positions, exp = _structure(legs, multiplier, costs)
    spots = sorted({0, *(strike for _, strike, _, _ in positions)})
    entry = sum(qty * premium for _, _, qty, premium in positions)
    fee = _units(costs, exp)
    values = [sum(_results(positions, s)) - fee for s in spots]
    tail = sum(qty for call, _, qty, _ in positions if call)
    roots: list[Fraction] = []
    for i, (spot, value) in enumerate(zip(spots, values, strict=True)):
        if value == 0:
            ends = values[i + 1] != 0 if i + 1 < len(values) else tail != 0
            if i == 0 or values[i - 1] != 0 or ends:
                roots.append(Fraction(spot))
        elif i and (value < 0 < values[i - 1] or value > 0 > values[i - 1]):
            x, y = spots[i - 1], values[i - 1]
            roots.append(x - Fraction(y * (spot - x), value - y))
    if tail and values[-1] * tail < 0:
        roots.append(spots[-1] - Fraction(values[-1], tail))
    equilibria = tuple(root * Fraction(10) ** exp if root else root for root in roots)
    gain = None if tail > 0 else _money(max(values), exp)
    loss = None if tail < 0 else _money(min(values), exp)
    return ExpiryProfile(_money(entry, exp), equilibria, gain, loss)
