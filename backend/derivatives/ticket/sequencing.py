"""Sequenciamento e contabilidade local de execuções conciliadas do simulador D0."""
from collections import Counter
from collections.abc import Mapping, Sequence
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
    strike: Annotated[Money, Field(gt=0)]
    balance: int


class Position(_Frozen):
    """Foto inicial da conta simulada; pares confirmados (proteção longa, série curta)."""

    account: Text
    holdings: tuple[Holding, ...]
    pairs: tuple[tuple[Text, Text], ...]

    def unpledged(self) -> dict[str, int]:
        """Saldos da foto descontadas todas as posições vendidas que cada série protege."""
        balances = {row.symbol: row.balance for row in self.holdings}
        free = balances.copy()
        last = {short: long for long, short in self.pairs}
        owed = {short: max(0, -balances[short]) for short in last}
        for long, short in self.pairs:
            debit = owed[short] if long == last[short] else min(max(0, free[long]), owed[short])
            free[long] -= debit
            owed[short] -= debit
        return free


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
    quotas: tuple[int, ...]

    def protections_for(self, leg: Leg) -> tuple[str, ...]:
        """Proteções usadas pela venda, na ordem de alocação do plano."""
        sources = tuple(buy for sale, buy, _ in self.dependencies if sale == leg.symbol)
        if not sources or leg not in self.legs:
            raise SequenceRefusal("venda sem proteção no plano")
        return sources

    def quota(self, leg: Leg, source: str) -> int:
        """Limita a venda à parte planejada somente quando outra venda usa a proteção."""
        if source not in self.protections_for(leg):
            raise SequenceRefusal("proteção ausente no plano")
        if any(buy == source and sale != leg.symbol for sale, buy, _ in self.dependencies):
            return next(q for (sale, buy, _), q in zip(self.dependencies, self.quotas, strict=True)
                        if (sale, buy) == (leg.symbol, source))
        return leg.quantity

    def protection_for(self, leg: Leg) -> str:
        """Primeira proteção usada pela venda."""
        return self.protections_for(leg)[0]


def plan_legs(draft: TicketDraft, position: Position) -> LegPlan:
    """Planeja por vínculo explícito de proteção; não interpreta o código de negociação."""
    draft = TicketDraft.model_validate(draft)
    position = Position.model_validate(position)
    position = Position(account=position.account, pairs=tuple(sorted(position.pairs)),
                        holdings=tuple(sorted(position.holdings, key=lambda h: h.symbol)))
    rows = {r.symbol: r for r in position.holdings}
    if len(rows) != len(position.holdings) or any(leg.symbol not in rows for leg in draft.legs):
        raise SequenceRefusal("posição ausente ou duplicada")
    longs = {long for long, _ in position.pairs}
    if (len(set(position.pairs)) != len(position.pairs)
            or any(short in longs for _, short in position.pairs)):
        raise SequenceRefusal("atribuição de proteção ambígua")
    sources: dict[str, list[str]] = {}
    uses = Counter(long for long, _ in position.pairs)
    for long, short in position.pairs:
        if short not in rows or long not in rows:
            raise SequenceRefusal("série sem evidência")
        a, b = rows[long], rows[short]
        sources.setdefault(short, []).append(long)
        if a.strike == b.strike or (a.underlying, a.kind, a.expiry, a.multiplier) != (
                b.underlying, b.kind, b.expiry, b.multiplier):
            raise SequenceRefusal("séries incompatíveis")
    for short, wings in sources.items():
        debt = -rows[short].balance
        if debt > 0 and len(wings) > 1 and (sum(rows[w].balance for w in wings) != debt
                                             or any(uses[w] > 1 for w in wings)):
            raise SequenceRefusal("vendida aberta com mais de uma proteção")
    free = position.unpledged()
    if any(free[long] < 0 for long in longs):
        raise SequenceRefusal("proteção inicial insuficiente")
    buys = {leg.symbol: leg for leg in draft.legs if leg.side is Side.BUY}
    sales = tuple(leg for leg in draft.legs if leg.side is Side.SELL)
    remaining = {symbol: leg.quantity for symbol, leg in buys.items()}
    for grant in draft.coverage:
        if grant.series not in rows:
            raise SequenceRefusal("série sem evidência")
        remaining[grant.series] = remaining.get(grant.series, 0) + grant.quantity
    dependencies: list[tuple[str, str, bool]] = []
    quotas: list[int] = []
    for buy in buys.values():
        balance = rows[buy.symbol].balance
        if balance < 0 and buy.quantity > -balance:
            raise SequenceRefusal("recompra atravessa saldo conciliado")
    for sale in sales:
        candidates: dict[str, bool] = {}
        for long, short in position.pairs:
            closing = sale.symbol == long
            source = short if closing else long
            if (sale.symbol != (long if closing else short) or source not in remaining
                    or source == sale.symbol):
                continue
            a, b = rows[source], rows[sale.symbol]
            if closing and (a.balance >= 0 or b.balance < sale.quantity):
                continue
            if not closing and (a.balance < 0 or b.balance > 0):
                continue
            candidates[source] = closing
        if not candidates and rows[sale.symbol].balance > 0:
            if sale.quantity > free[sale.symbol]:
                raise SequenceRefusal("saldo livre insuficiente")
            dependencies.append((sale.symbol, sale.symbol, True))
            quotas.append(sale.quantity)
            continue
        if not candidates or (len(candidates) > 1 and any(candidates.values())):
            raise SequenceRefusal("pareamento ausente ou ambíguo")
        # remaining conserva a ordem das compras e depois das séries só autorizadas.
        needed = sale.quantity
        for source in remaining:
            if source in candidates and needed and remaining[source]:
                take = min(needed, remaining[source])
                remaining[source] -= take
                needed -= take
                dependencies.append((sale.symbol, source, candidates[source]))
                quotas.append(take)
        if needed:
            raise SequenceRefusal("quantidade de proteção insuficiente")
    if {g.series for g in draft.coverage} - {buy for sale, buy, _ in dependencies if sale != buy}:
        raise SequenceRefusal("autorização sem venda correspondente")
    return LegPlan(draft, (*buys.values(), *sales), position, tuple(dependencies), tuple(quotas))


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
    origin: str
    leg: Leg
    source: str
    filled: int
    live: int


class ReservationBook:
    """Livro por replay; a mesma instância arbitra todas as boletas concorrentes."""

    def __init__(self) -> None:
        """Inicia saldos vazios sem carregar posições externas."""
        self._lock = Lock()
        self._frozen: set[tuple[str, str]] = set()
        self._plans: dict[tuple[str, str], LegPlan] = {}
        self._occupation: dict[tuple[str, str, str], int] = {}
        self._buys: dict[tuple[str, str, str], int] = {}
        self._orders: dict[tuple[str, str], _Order] = {}
        self._executions: set[tuple[str, str]] = set()
        self._positions: dict[str, Position] = {}
        self._closed: set[tuple[str, str]] = set()

    def freeze(self, account: str, symbol: str) -> None:
        """Congela novos usos da série nesta conta até a próxima foto."""
        with self._lock:
            self._frozen.add((account, symbol))

    def _frozen_in_plan(self, plan: LegPlan) -> tuple[str, ...]:
        symbols = {leg.symbol for leg in plan.legs}
        symbols.update(source for _, source, _ in plan.dependencies)
        return tuple(sorted(s for s in symbols if (plan.position.account, s) in self._frozen))

    def frozen(self, plan: LegPlan) -> tuple[str, ...]:
        """Lista as séries congeladas que o plano usa em pernas ou proteções."""
        with self._lock:
            return self._frozen_in_plan(plan)

    def close(self, account: str, ticket: str) -> None:
        """Encerra a origem sem descartar ordens vivas nem impedir conciliação tardia."""
        with self._lock:
            if (account, ticket) not in self._plans:
                raise SequenceRefusal("boleta desconhecida")
            self._closed.add((account, ticket))

    def _surplus(self, account: str, origin: str, source: str) -> int:
        used = sum(o.live + o.filled for (a, _), o in self._orders.items()
                   if a == account and o.origin == origin and o.source == source)
        return self._buys.get((account, origin, source), 0) - used

    def _check(self, plan: LegPlan, ticket: str) -> str:
        account = plan.position.account
        if type(ticket) is not str or not ticket or plan != plan_legs(plan.draft, plan.position):
            raise SequenceRefusal("identidade ou plano divergente")
        if self._positions.get(account, plan.position) != plan.position:
            raise SequenceRefusal("foto divergente; conciliação necessária")
        if self._plans.get((account, ticket), plan) != plan:
            raise SequenceRefusal("identidade ou plano divergente")
        return account

    def _remember(self, plan: LegPlan, ticket: str) -> None:
        account = plan.position.account
        self._plans[account, ticket] = plan
        self._positions[account] = plan.position

    def _free_long(self, plan: LegPlan, symbol: str) -> int:
        committed = sum(o.live + o.filled for (account, _), o in self._orders.items()
                        if account == plan.position.account and o.leg.symbol == o.source == symbol)
        return plan.position.unpledged()[symbol] - committed

    def _admission(self, plan: LegPlan, ticket: str) -> dict[tuple[str, str, str], int]:
        account = self._check(plan, ticket)
        if self._frozen_in_plan(plan):
            raise SequenceRefusal("série com fato externo; foto nova necessária")
        balances = {h.symbol: h.balance for h in plan.position.holdings}
        for grant in plan.draft.coverage:
            if grant.origin == ticket or (account, grant.origin) not in self._closed:
                raise SequenceRefusal("boleta de origem não parada")
            if self._surplus(account, grant.origin, grant.series) <= 0:
                raise SequenceRefusal("sobra indisponível")
        for sale, source, _ in plan.dependencies:
            if sale == source and self._free_long(plan, sale) <= 0:
                raise SequenceRefusal("saldo livre indisponível")
        occupation = {}
        for leg in plan.legs:
            if leg.side is not Side.BUY:
                continue
            initial = balances[leg.symbol]
            if initial < 0:
                other = sum(n for (a, t, s), n in self._occupation.items()
                            if a == account and t != ticket and s == leg.symbol)
                if other + leg.quantity > -initial:
                    raise SequenceRefusal("recompra excede a posição vendida disponível")
            occupation[account, ticket, leg.symbol] = leg.quantity
        return occupation

    def admissible(self, plan: LegPlan, *, ticket: str) -> None:
        """Confere foto e capacidade sem ocupar saldo nem registrar o plano."""
        with self._lock:
            self._admission(plan, ticket)

    def admit(self, plan: LegPlan, *, ticket: str) -> None:
        """Reconfere e ocupa todas as compras em uma só seção crítica."""
        with self._lock:
            occupation = self._admission(plan, ticket)
            self._remember(plan, ticket)
            self._occupation.update(occupation)

    def settle_buy(self, account: str, ticket: str, symbol: str) -> None:
        """Conserva somente o executado quando a compra alcança estado final."""
        key = account, ticket, symbol
        with self._lock:
            if key not in self._occupation:
                raise SequenceRefusal("compra sem ocupação")
            self._occupation[key] = self._buys.get(key, 0)

    def confirm_buy(self, plan: LegPlan, leg: Leg, execution: str, quantity: int, *,
                    ticket: str) -> None:
        """Credita uma execução de compra conciliada uma única vez."""
        with self._lock:
            account = self._check(plan, ticket)
            key = account, ticket, leg.symbol
            total = self._buys.get(key, 0)
            if (leg not in plan.legs or leg.side is not Side.BUY or not execution
                    or (account, execution) in self._executions or type(quantity) is not int
                    or quantity <= 0 or total + quantity > leg.quantity
                    or total + quantity > self._occupation.get(key, leg.quantity)):
                raise SequenceRefusal("execução de compra inválida")
            initial = next(h.balance for h in plan.position.holdings if h.symbol == leg.symbol)
            if initial < 0 and self._bought(account, leg.symbol) + quantity > -initial:
                raise SequenceRefusal("execuções excedem posição vendida")
            self._remember(plan, ticket)
            self._buys[key] = total + quantity
            self._executions.add((account, execution))

    def _bought(self, account: str, symbol: str) -> int:
        return sum(n for (a, _, s), n in self._buys.items() if (a, s) == (account, symbol))

    def _capacity(self, plan: LegPlan, leg: Leg, ticket: str,
                  origin: str | None, source: str | None) -> tuple[int, str]:
        account = self._check(plan, ticket)
        sources = plan.protections_for(leg)
        if source is None:
            source = sources[0]
        if (source not in sources or (account, ticket) in self._closed
                or (account, leg.symbol) in self._frozen or (account, source) in self._frozen):
            return 0, source
        balances = {h.symbol: h.balance for h in plan.position.holdings}
        closing = balances[source] < 0
        orders = [o for (a, _), o in self._orders.items() if a == account]
        if leg.symbol == source:
            free = self._free_long(plan, source) if origin is None else 0
        elif origin is None:
            free = self._surplus(account, ticket, source)
        elif origin == ticket or (account, origin) not in self._closed:
            free = 0
        else:
            limit = next((g.quantity for g in plan.draft.coverage
                          if g.series == source and g.origin == origin), 0)
            used = sum(o.live + o.filled for o in orders
                       if o.ticket == ticket and o.source == source and o.origin == origin)
            free = min(self._surplus(account, origin, source), limit - used)
        if closing:
            disposed = sum(o.filled + o.live for o in orders if o.leg.symbol == leg.symbol)
            # Teto redundante: a recompra cabe no vendido, já coberto pelo saldo comprado.
            free = min(free, balances[leg.symbol] - disposed)
        own = [o for o in orders if o.ticket == ticket and o.leg == leg]
        occupied = sum(o.live + o.filled for o in own)
        on_source = sum(o.live + o.filled for o in own if o.source == source)
        room = min(free, leg.quantity - occupied, plan.quota(leg, source) - on_source)
        return max(0, room - room % leg.lot_size), source

    def available(self, plan: LegPlan, leg: Leg, *, ticket: str, origin: str | None = None,
                  source: str | None = None) -> int:
        """Consulta a quantidade que o livro compartilhado pode reservar agora."""
        with self._lock:
            return self._capacity(plan, leg, ticket, origin, source)[0]

    def reserve(self, plan: LegPlan, leg: Leg, order: str, quantity: int, *,
                ticket: str, origin: str | None = None, source: str | None = None) -> None:
        """Confere e ocupa o saldo na mesma seção crítica."""
        with self._lock:
            free, source = self._capacity(plan, leg, ticket, origin, source)
            key = plan.position.account, order
            if (not order or key in self._orders or type(quantity) is not int
                    or not 0 < quantity <= free or quantity % leg.lot_size):
                raise SequenceRefusal("reserva indisponível")
            self._remember(plan, ticket)
            owner = ticket if origin is None else origin
            self._orders[key] = _Order(ticket, owner, leg, source, 0, quantity)

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


class Gross(NamedTuple):
    """Limite assinado, volume executado e volume projetado da boleta em reais."""

    signed: Decimal
    executed: Decimal
    projected: Decimal

    def receipt_values(self) -> dict[str, str]:
        """Representação monetária canônica do recibo."""
        return {"signed": f"{self.signed:.2f}", "executed": f"{self.executed:.2f}",
                "projected": f"{self.projected:.2f}"}


def gross_amounts(draft: TicketDraft, fills: Sequence[Fill],
                  open_balances: Mapping[str, int] | None) -> Gross:
    """Após o término, projeta somente os saldos abertos informados pelo motor."""
    remaining = {leg.symbol: leg.quantity for leg in draft.legs}
    with localcontext(_exact()):
        executed = Decimal(0)
        for fill in fills:
            executed += fill.price * fill.quantity
            remaining[fill.symbol] -= fill.quantity
        balances = remaining if open_balances is None else open_balances
        projected = sum((leg.limit_price * balances.get(leg.symbol, 0) for leg in draft.legs),
                        executed)
        return Gross(draft.gross_cap, executed, projected)


def partial_exposure(draft: TicketDraft, *, known_costs: Decimal = Decimal(0),
                     zeroing: bool = False) -> Decimal:
    """Desembolso máximo se nenhuma venda executar, incluindo o custo conhecido."""
    draft = TicketDraft.model_validate(draft)
    buys = tuple(leg for leg in draft.legs if leg.side is Side.BUY)
    if (not buys and not draft.coverage and not zeroing) or not _valid_cost(known_costs):
        raise SequenceRefusal("exposição sem compra protetora ou custo válido")
    with localcontext(_exact()):
        return sum((leg.quantity * leg.limit_price for leg in buys), known_costs)


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
