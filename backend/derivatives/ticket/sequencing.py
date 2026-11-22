"""Sequenciamento e contabilidade local de execuções conciliadas do simulador D0."""
from dataclasses import dataclass
from datetime import date
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal, localcontext
from threading import Lock
from typing import Annotated, Literal, NamedTuple

from pydantic import Field, ValidationError

from backend.derivatives.ticket.models import (
    Leg, Money, PositiveInt, Side, Text, TicketDraft, _Frozen,
)


class SequenceRefusal(ValueError):
    """Evidência insuficiente, posição incompatível ou saldo indisponível."""


class Holding(_Frozen):
    """Saldo inicial conciliado em unidades e identidade comprovada da série."""

    symbol: Text
    underlying: Text
    kind: Literal["CALL", "PUT"]
    expiry: date
    multiplier: PositiveInt
    balance: int


class Position(_Frozen):
    """Foto inicial da conta simulada; pares confirmados (proteção longa, série curta)."""

    account: Text
    holdings: tuple[Holding, ...]
    pairs: tuple[tuple[Text, Text], ...]


class Fill(_Frozen):
    """Execução confirmada da versão desta boleta, em unidades e reais por unidade."""

    execution: Text
    symbol: Text
    side: Side
    quantity: PositiveInt
    price: Annotated[Money, Field(gt=0)]


class LegPlan(NamedTuple):
    """Ordem estável, foto de origem e dependências (venda, compra, desmontagem)."""

    draft: TicketDraft
    legs: tuple[Leg, ...]
    position: Position
    dependencies: tuple[tuple[str, str, bool], ...]

    def protection_for(self, leg: Leg) -> str:
        """Identifica a compra cuja execução libera a venda desta boleta."""
        for sale, buy, _ in self.dependencies:
            if sale == leg.symbol and leg in self.legs:
                return buy
        raise SequenceRefusal("venda sem proteção no plano")


def plan_legs(draft: TicketDraft, position: Position) -> LegPlan:
    """Planeja por vínculo explícito de proteção; não interpreta o código de negociação."""
    draft = TicketDraft.model_validate(draft)
    position = Position.model_validate(position)
    position = Position(account=position.account, pairs=tuple(sorted(position.pairs)),
                        holdings=tuple(sorted(position.holdings, key=lambda h: h.symbol)))
    rows = {r.symbol: r for r in position.holdings}
    if len(rows) != len(position.holdings) or any(leg.symbol not in rows for leg in draft.legs):
        raise SequenceRefusal("posição ausente ou duplicada")
    pledged: dict[str, int] = {}
    owners = {short: long for long, short in position.pairs}
    if len(owners) != len(position.pairs) or set(owners) & set(owners.values()):
        raise SequenceRefusal("atribuição de proteção ambígua")
    for short, long in owners.items():
        if short not in rows or long not in rows:
            raise SequenceRefusal("série sem evidência")
        a, b = rows[long], rows[short]
        if (a.underlying, a.kind, a.expiry, a.multiplier) != (
                b.underlying, b.kind, b.expiry, b.multiplier):
            raise SequenceRefusal("séries incompatíveis")
        pledged[long] = pledged.get(long, 0) + max(0, -b.balance)
    if any(n > rows[s].balance for s, n in pledged.items()):
        raise SequenceRefusal("proteção inicial insuficiente")
    buys = {leg.symbol: leg for leg in draft.legs if leg.side is Side.BUY}
    sales = tuple(leg for leg in draft.legs if leg.side is Side.SELL)
    remaining = {symbol: leg.quantity for symbol, leg in buys.items()}
    dependencies: list[tuple[str, str, bool]] = []
    for buy in buys.values():
        balance = rows[buy.symbol].balance
        if balance < 0 and buy.quantity > -balance:
            raise SequenceRefusal("recompra atravessa saldo conciliado")
    for sale in sales:
        candidates = []
        for long, short in position.pairs:
            closing = sale.symbol == long
            source = short if closing else long
            if (sale.symbol != (long if closing else short) or source not in buys
                    or source == sale.symbol):
                continue
            a, b = rows[source], rows[sale.symbol]
            if closing and (a.balance >= 0 or b.balance < sale.quantity):
                continue
            if not closing and (a.balance < 0 or b.balance > 0):
                continue
            candidates.append((source, closing))
        if len(candidates) != 1:
            raise SequenceRefusal("pareamento ausente ou ambíguo")
        source, closing = candidates[0]
        remaining[source] -= sale.quantity
        if remaining[source] < 0:
            raise SequenceRefusal("quantidade de proteção insuficiente")
        dependencies.append((sale.symbol, source, closing))
    return LegPlan(draft, (*buys.values(), *sales), position, tuple(dependencies))


def releasable_quantity(leg: Leg, fills: int, sold: int, reservations: int) -> int:
    """Calcula unidades livres a partir de compras executadas, vendas e saldos vivos."""
    leg = Leg.model_validate(leg)
    if (leg.side is not Side.SELL or any(type(q) is not int or q < 0
                                        for q in (fills, sold, reservations))
            or sold + reservations > fills):
        raise SequenceRefusal("saldos de cobertura inconsistentes")
    free = min(leg.quantity, fills - sold - reservations)
    return free - free % leg.lot_size


class _Order(NamedTuple):
    ticket: str
    leg: Leg
    source: str
    filled: int
    live: int


class ReservationBook:
    """Livro por replay; a mesma instância arbitra todas as boletas concorrentes."""

    def __init__(self) -> None:
        """Inicia saldos vazios sem carregar posições externas."""
        self._lock = Lock()
        self._plans: dict[tuple[str, str], LegPlan] = {}
        self._buys: dict[tuple[str, str, str], int] = {}
        self._orders: dict[tuple[str, str], _Order] = {}
        self._executions: set[tuple[str, str]] = set()
        self._positions: dict[str, Position] = {}

    def _check(self, plan: LegPlan, ticket: str) -> str:
        account = plan.position.account
        if (type(ticket) is not str or not ticket or plan != plan_legs(plan.draft, plan.position)
                or self._plans.get((account, ticket), plan) != plan):
            raise SequenceRefusal("identidade ou plano divergente")
        if self._positions.get(account, plan.position) != plan.position:
            raise SequenceRefusal("foto divergente; conciliação necessária")
        return account

    def _remember(self, plan: LegPlan, ticket: str) -> None:
        account = plan.position.account
        self._plans[account, ticket] = plan
        self._positions[account] = plan.position

    def confirm_buy(self, plan: LegPlan, leg: Leg, execution: str, quantity: int, *,
                    ticket: str) -> None:
        """Credita uma execução de compra conciliada uma única vez."""
        with self._lock:
            account = self._check(plan, ticket)
            key = account, ticket, leg.symbol
            total = self._buys.get(key, 0)
            if (leg not in plan.legs or leg.side is not Side.BUY or not execution
                    or (account, execution) in self._executions or type(quantity) is not int
                    or quantity <= 0 or total + quantity > leg.quantity):
                raise SequenceRefusal("execução de compra inválida")
            initial = next(h.balance for h in plan.position.holdings if h.symbol == leg.symbol)
            if initial < 0 and self._bought(account, leg.symbol) + quantity > -initial:
                raise SequenceRefusal("execuções excedem posição vendida")
            self._remember(plan, ticket)
            self._buys[key] = total + quantity
            self._executions.add((account, execution))

    def _bought(self, account: str, symbol: str) -> int:
        return sum(n for (a, _, s), n in self._buys.items() if (a, s) == (account, symbol))

    def _capacity(self, plan: LegPlan, leg: Leg, ticket: str) -> tuple[int, str]:
        account = self._check(plan, ticket)
        source = plan.protection_for(leg)
        balances = {h.symbol: h.balance for h in plan.position.holdings}
        closing = balances[source] < 0
        orders = [o for (a, _), o in self._orders.items() if a == account]
        # Uma recompra só libera uma proteção, inclusive entre boletas.
        used = sum(o.live + o.filled for o in orders if o.source == source)
        bought = self._bought(account, source)
        free = releasable_quantity(leg, bought, used, 0)
        if closing:
            disposed = sum(o.filled + o.live for o in orders if o.leg.symbol == leg.symbol)
            free = min(free, balances[leg.symbol] - disposed)
        own = sum(o.live + o.filled for o in orders if o.ticket == ticket and o.leg == leg)
        room = min(free, leg.quantity - own)
        return max(0, room - room % leg.lot_size), source

    def available(self, plan: LegPlan, leg: Leg, *, ticket: str) -> int:
        """Consulta a quantidade que o livro compartilhado pode reservar agora."""
        with self._lock:
            return self._capacity(plan, leg, ticket)[0]

    def reserve(self, plan: LegPlan, leg: Leg, order: str, quantity: int, *, ticket: str) -> None:
        """Confere e ocupa o saldo na mesma seção crítica."""
        with self._lock:
            free, source = self._capacity(plan, leg, ticket)
            key = plan.position.account, order
            if (not order or key in self._orders or type(quantity) is not int
                    or not 0 < quantity <= free or quantity % leg.lot_size):
                raise SequenceRefusal("reserva indisponível")
            self._remember(plan, ticket)
            self._orders[key] = _Order(ticket, leg, source, 0, quantity)

    def confirm_sale(self, account: str, order: str, execution: str, quantity: int) -> None:
        """Converte saldo vivo em executado sem creditar novamente a proteção."""
        with self._lock:
            o = self._orders.get((account, order))
            if (not execution or (account, execution) in self._executions or o is None
                    or type(quantity) is not int or not 0 < quantity <= o.live):
                raise SequenceRefusal("execução de venda inconsistente")
            self._orders[account, order] = o._replace(
                filled=o.filled + quantity, live=o.live - quantity)
            self._executions.add((account, execution))

    def confirm_release(self, account: str, order: str, remaining: int) -> None:
        """Libera exclusivamente o saldo final confirmado da ordem identificada."""
        with self._lock:
            o = self._orders.get((account, order))
            if o is None or type(remaining) is not int or remaining != o.live or remaining <= 0:
                raise SequenceRefusal("saldo final divergente")
            self._orders[account, order] = o._replace(live=0)


def _exact() -> Context:
    return Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX)


def partial_exposure(draft: TicketDraft, *, known_costs: Decimal = Decimal(0)) -> Decimal:
    """Desembolso máximo da primeira compra no plano estável, incluindo seu custo conhecido."""
    draft = TicketDraft.model_validate(draft)
    first = next((leg for leg in draft.legs if leg.side is Side.BUY), None)
    if first is None or not _valid_cost(known_costs):
        raise SequenceRefusal("exposição sem compra protetora ou custo válido")
    with localcontext(_exact()):
        return first.quantity * first.limit_price + known_costs


def within_signed_limits(draft: TicketDraft, fills: tuple[Fill, ...], next_leg: Leg, *,
                         known_costs: Decimal) -> bool:
    """Testa preços individuais e projeção dos limites totais usando execuções desta boleta."""
    try:
        draft = TicketDraft.model_validate(draft)
        next_leg = Leg.model_validate(next_leg)
        signed = {leg.symbol: leg for leg in draft.legs}
        target = signed[next_leg.symbol]
        if (next_leg.side != target.side or next_leg.lot_size != target.lot_size
                or not _valid_cost(known_costs)):
            return False
        remaining = {leg.symbol: leg.quantity for leg in draft.legs}
        with localcontext(_exact()):
            net = gross = known_costs
            seen: set[str] = set()
            for fact in fills:
                fill = Fill.model_validate(fact)
                leg = signed[fill.symbol]
                if (fill.execution in seen or fill.side != leg.side
                        or fill.quantity > remaining[fill.symbol]
                        or not _price_ok(leg, fill.price)):
                    return False
                seen.add(fill.execution)
                remaining[fill.symbol] -= fill.quantity
                amount = fill.price * fill.quantity
                net += amount if leg.side is Side.BUY else -amount
                gross += amount
            if (next_leg.quantity > remaining[target.symbol]
                    or not _price_ok(target, next_leg.limit_price)):
                return False
            for leg in draft.legs:
                amount = remaining[leg.symbol] * leg.limit_price
                net += amount if leg.side is Side.BUY else -amount
                gross += amount
            extra = max(Decimal(0), next_leg.limit_price - target.limit_price) * next_leg.quantity
            return net <= draft.net_limit and gross + extra <= draft.gross_cap
    except (KeyError, ValidationError, ArithmeticError):
        return False


def _price_ok(leg: Leg, price: Decimal) -> bool:
    return price <= leg.limit_price if leg.side is Side.BUY else price >= leg.limit_price


def _valid_cost(value: Decimal) -> bool:
    return type(value) is Decimal and value.is_finite() and value >= 0
