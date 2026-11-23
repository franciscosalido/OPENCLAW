"""Compara o plano assinado com fatos de execução confirmados para o mesmo vencimento."""
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import islice

from backend.derivatives.pricing.expiry_payoff import (
    ExpiryLeg, ExpiryProfile, PayoffRefusal, expiry_profile,
)


def _symbol(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise PayoffRefusal("símbolo exige texto não vazio")


@dataclass(frozen=True, slots=True)
class PlannedLeg:
    """Série do plano e perna com o prêmio assinado."""
    symbol: str
    leg: ExpiryLeg

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        if not isinstance(self.leg, ExpiryLeg):
            raise PayoffRefusal("perna planejada inválida")


@dataclass(frozen=True, slots=True)
class Execution:
    """Quantidade confirmada em uma série, ao preço efetivo por unidade."""
    symbol: str
    quantity: int
    price: Decimal

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        if type(self.quantity) is not int or self.quantity <= 0:
            raise PayoffRefusal("quantidade executada exige inteiro positivo")
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price < 0:
            raise PayoffRefusal("preço efetivo exige Decimal finito não negativo")


@dataclass(frozen=True, slots=True)
class PartialView:
    """Dois perfis de vencimento e quantidades que ainda dependem de execução."""
    planned: ExpiryProfile
    executed_legs: tuple[ExpiryLeg, ...]
    executed: ExpiryProfile | None
    pending: tuple[tuple[str, int], ...]


def _items[T](items: Iterable[T]) -> Iterator[T]:
    if isinstance(items, (str, bytes, bytearray, Mapping)):
        raise PayoffRefusal("coleção inválida")
    try:
        yield from items
    except Exception as exc:
        raise PayoffRefusal("coleção ilegível") from exc


def partial_view(plan: Iterable[PlannedLeg], executions: Iterable[Execution], *,
                 multiplier: int = 1) -> PartialView:
    """Reconstitui a posição apenas pelas execuções fornecidas, sem estimar preenchimentos."""
    legs = tuple(islice(_items(plan), 9))
    if not 1 <= len(legs) <= 8 or not all(isinstance(p, PlannedLeg) for p in legs):
        raise PayoffRefusal("plano exige de uma a oito pernas válidas")
    remaining = {p.symbol: p.leg.quantity for p in legs}
    if len(remaining) != len(legs):
        raise PayoffRefusal("símbolo repetido no plano")
    planned = expiry_profile([p.leg for p in legs], multiplier=multiplier)
    prices: dict[str, dict[Decimal, int]] = {p.symbol: {} for p in legs}
    for fill in _items(executions):
        if not isinstance(fill, Execution) or fill.symbol not in remaining:
            raise PayoffRefusal("execução inválida ou série fora do plano")
        if fill.quantity > remaining[fill.symbol]:
            raise PayoffRefusal("quantidade executada excede o plano")
        remaining[fill.symbol] -= fill.quantity
        bucket = prices[fill.symbol]
        bucket[fill.price] = bucket.get(fill.price, 0) + fill.quantity
        if sum(map(len, prices.values())) > 64:
            raise PayoffRefusal("mais de 64 pares de série e preço")
    actual = tuple(replace(p.leg, premium=price, quantity=qty) for p in legs
                   for price, qty in sorted(prices[p.symbol].items()))
    executed = expiry_profile(actual, multiplier=multiplier, max_legs=64) if actual else None
    return PartialView(planned, actual, executed, tuple((s, q) for s, q in remaining.items() if q))
