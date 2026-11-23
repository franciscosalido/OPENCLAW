"""Agregação de preços já conferidos pelas pontes, em reais e antes do vencimento."""
import decimal as dec
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import islice
from math import isfinite

from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.expiry_payoff import ExpiryLeg, PayoffRefusal


@dataclass(frozen=True, slots=True)
class PreExpiryEstimate:
    """Valores da estrutura e referências aos preços usados, na ordem das pernas."""
    net_entry: dec.Decimal
    theoretical_value: dec.Decimal
    result: dec.Decimal
    leg_results: tuple[dec.Decimal, ...]
    outcomes: tuple[PricingOutcome, ...]


def _snapshot[T](items: Sequence[T], limit: int) -> tuple[T, ...]:
    try:
        if isinstance(items, Sequence):
            return tuple(islice(items, limit + 1))
    except Exception as exc:
        raise PayoffRefusal("sequência ilegível") from exc
    raise PayoffRefusal("esperada sequência de pernas ou preços")


def _money(terms: Iterable[tuple[int, dec.Decimal]]) -> dec.Decimal:
    # Coeficientes inteiros por expoente permitem cancelar antes de alinhar as escalas.
    groups: dict[int, int] = {}
    for quantity, value in terms:
        if value:
            sign, digits, exp = value.as_tuple()
            power = int(exp)
            groups[power] = groups.get(power, 0) + quantity * int(dec.Decimal((sign, digits, 0)))
    ctx = dec.Context(prec=dec.MAX_PREC, Emin=dec.MIN_EMIN, Emax=dec.MAX_EMAX,
                          traps=[dec.Inexact, dec.InvalidOperation, dec.Overflow])
    coefficient, exponent = dec.Decimal(0), 0
    try:
        for power, part in sorted(groups.items(), reverse=True):
            if part:
                prior = ctx.scaleb(coefficient, exponent - power) if coefficient else dec.Decimal(0)
                coefficient = ctx.add(prior, part)
                exponent = power
        sign, digits, offset = coefficient.as_tuple()
        return dec.Decimal((sign, digits, exponent + int(offset)), context=ctx)
    except (dec.DecimalException, MemoryError, OverflowError) as exc:
        raise PayoffRefusal("resultado fora da representação Decimal") from exc


def pre_expiry_estimate(legs: Sequence[ExpiryLeg], outcomes: Sequence[PricingOutcome], *,
                        multiplier: int = 1, costs: dec.Decimal = dec.Decimal(0),
                        max_legs: int = 8) -> PreExpiryEstimate:
    """Estima a posição com um preço suportado por perna e um único custo total."""
    if type(max_legs) is not int or not 1 <= max_legs <= 64:
        raise PayoffRefusal("max_legs exige inteiro de 1 a 64")
    if type(multiplier) is not int or multiplier < 1:
        raise PayoffRefusal("multiplicador exige inteiro positivo")
    if not isinstance(costs, dec.Decimal) or not costs.is_finite() or costs < 0:
        raise PayoffRefusal("custo exige Decimal finito não negativo")
    positions, marks = _snapshot(legs, max_legs), _snapshot(outcomes, max_legs)
    if not 1 <= len(positions) <= max_legs or len(marks) != len(positions):
        raise PayoffRefusal("quantidades de pernas e preços incompatíveis")
    entries: list[tuple[int, dec.Decimal]] = []
    values: list[tuple[int, dec.Decimal]] = []
    parts: list[dec.Decimal] = []
    for i, (leg, mark) in enumerate(zip(positions, marks, strict=True), 1):
        if not isinstance(leg, ExpiryLeg) or not isinstance(mark, PricingOutcome):
            raise PayoffRefusal(f"perna {i}: perna ou preço inválido")
        if not mark.supported:
            raise PayoffRefusal(f"perna {i}: {mark.reason}")
        price, echo = mark.price, mark.inputs_echo
        if not isinstance(price, dec.Decimal) or not price.is_finite() or price < 0:
            raise PayoffRefusal(f"perna {i}: preço ausente ou inválido")
        if echo.get("kind") != leg.kind or echo.get("strike") != float(leg.strike):
            raise PayoffRefusal(f"perna {i}: tipo ou strike incompatível")
        for key in ("spot", "time_years"):
            ref = echo.get(key)
            if not isinstance(ref, float) or not isfinite(ref) or ref != marks[0].inputs_echo[key]:
                raise PayoffRefusal(f"perna {i}: {key} ausente, inválido ou divergente")
        qty = multiplier * (leg.quantity if leg.side == "BUY" else -leg.quantity)
        entries.append((qty, leg.premium))
        values.append((qty, price))
        parts.append(_money(((qty, price), (-qty, leg.premium))))
    entry, value = _money(entries), _money(values)
    result = _money(((1, value), (-1, entry), (-1, costs)))
    return PreExpiryEstimate(entry, value, result, tuple(parts), marks)
