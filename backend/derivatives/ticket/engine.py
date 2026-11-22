"""Orquestra uma única boleta assinada no replay síncrono D0."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import re
from types import MappingProxyType

from backend.derivatives.ticket.gate import Action, DecisionLedger, HumanDecision
from backend.derivatives.ticket.guards import BookView, assess, check_deadlines
from backend.derivatives.ticket.models import (
    FieldRef, Leg, MarketSuggestion, Preview, Side, TicketDraft, apply_human_edit,
    apply_market_refresh,
)
from backend.derivatives.ticket.receipt import Receipt
from backend.derivatives.ticket.replay import ReplayEvent
from backend.derivatives.ticket.sequencing import (
    Fill, LegPlan, Position, ReservationBook, SequenceRefusal, partial_exposure, plan_legs,
    within_signed_limits,
)
from backend.derivatives.ticket.state import (
    Event as E, InvalidTransition, OrderState as O, TicketState as T, reconcile, transition,
)
from backend.derivatives.ticket.trigger import Outcome, Trigger, TriggerSpec, spec_digest
from backend.derivatives.ticket.venue import ExecutionVenue, VenueOrder, VenueReport
from config.ticket_sim_config_model import TicketSimConfig

_LIVE = {O.PENDING_SEND, O.LIVE, O.PARTIAL, O.CANCEL_REQUESTED, O.UNCERTAIN}
_ZERO = Decimal(0)
_ID_COMPONENT = re.compile(r"[A-Za-z0-9._-]+")


class EngineRefusal(ValueError):
    """O estado ou os limites vigentes impedem a ação."""


def _check_id_component(value: str) -> None:
    if not isinstance(value, str) or not _ID_COMPONENT.fullmatch(value):
        raise EngineRefusal("identificador da boleta ou símbolo fora do alfabeto permitido")


def _send_window_open(draft: TicketDraft, now: datetime) -> bool:
    return now <= draft.send_deadline and now < draft.order_validity


class AccountHalts:
    """Compartilha bloqueios por incerteza e divergência entre motores da conta."""
    def __init__(self) -> None:
        self._pending: set[tuple[str, str]] = set()

    def blocked(self, account: str) -> bool:
        """Indica se alguma causa ainda bloqueia esta conta."""
        return any(a == account for a, _ in self._pending)

    def divergent(self, account: str) -> bool:
        return (account, "divergence") in self._pending

    def hold(self, account: str, key: str) -> None:
        """Registra a causa que bloqueia novos envios da conta."""
        self._pending.add((account, key))

    def release(self, account: str, key: str) -> None:
        """Libera somente o bloqueio associado à chave informada."""
        self._pending.discard((account, key))


@dataclass
class _Order:
    request: VenueOrder
    leg: Leg
    state: O = O.PENDING_SEND
    filled: int = 0
    executions: int = 0
    pending: list[VenueReport] = field(default_factory=list)


class TicketEngine:
    """Mantém versão, alocações e fatos da venue para a boleta identificada."""
    def __init__(self, ticket: str, position: Position, *, venue: ExecutionVenue,
                 book: BookView, reservations: ReservationBook, ledger: DecisionLedger,
                 halts: AccountHalts, receipt: Receipt, config: TicketSimConfig) -> None:
        _check_id_component(ticket)
        self._ticket = ticket
        self._position = Position.model_validate(position)
        self._account = position.account
        self._venue = venue
        self._book = book
        self._reservations = reservations
        self._ledger = ledger
        self._halts = halts
        self._receipt = receipt
        self._config = config
        self._state = T.DRAFT
        self._paused = False
        self._cancelled = False
        self._preview: Preview | None = None
        self._plan: LegPlan | None = None
        self._trigger: Trigger | None = None
        self._orders: dict[str, _Order] = {}
        self._fills: list[Fill] = []

    @property
    def state(self) -> T:
        """Estado factual da boleta."""
        return self._state

    @property
    def paused(self) -> bool:
        """Indica suspensão de novos envios."""
        return self._paused

    @property
    def preview(self) -> Preview | None:
        """Versão atual exibida ao humano."""
        return self._preview

    @property
    def orders(self) -> Mapping[str, O]:
        """Foto dos estados por identificador da venue."""
        return MappingProxyType({oid: o.state for oid, o in self._orders.items()})

    def _require(self, *states: T) -> LegPlan:
        if self._state not in states or self._plan is None:
            raise EngineRefusal("estado incompatível")
        return self._plan

    def _record(self, event: E, now: datetime, **data: object) -> None:
        self._receipt.append(now, event, {"ticket": self._ticket, **data})

    def _move(self, event: E, now: datetime, **data: object) -> None:
        state = transition(self._state, event)
        assert isinstance(state, T)
        self._record(event, now, state=state.value, **data)
        self._set_state(state)

    def _set_state(self, state: T) -> None:
        self._state = state
        if state == T.STOPPED and not self._halts.divergent(self._account):
            assert self._plan is not None
            sent = {o.leg.symbol for o in self._orders.values()}
            for leg in self._plan.legs:
                if leg.side is Side.BUY and leg.symbol not in sent:
                    self._reservations.settle_buy(self._account, self._ticket, leg.symbol)

    def _propose(self, draft: TicketDraft, now: datetime) -> None:
        draft = TicketDraft.model_validate(draft)
        for leg in draft.legs:
            _check_id_component(leg.symbol)
        plan = plan_legs(draft, self._position)
        preview = Preview.from_draft(plan.draft, partial_exposure=partial_exposure(plan.draft))
        self._receipt.append_preview(now, preview)
        self._plan, self._preview = plan, preview

    def propose(self, draft: TicketDraft, now: datetime) -> None:
        """Valida plano e exposição antes de registrar a primeira prévia."""
        if self._state != T.DRAFT or self._preview is not None:
            raise EngineRefusal("proposta já apresentada")
        self._propose(draft, now)

    def edit(self, field: FieldRef, value: object, now: datetime) -> None:
        """Cria uma versão pelo fluxo de edição humana."""
        draft = self._require(T.DRAFT, T.TRIGGERED).draft
        self._propose(apply_human_edit(draft, field, value), now)

    def refresh(self, suggestion: MarketSuggestion, now: datetime) -> None:
        """Registra somente atualização que efetivamente alterou a versão."""
        draft = self._require(T.DRAFT, T.TRIGGERED).draft
        new = apply_market_refresh(draft, suggestion)
        if new.version != draft.version:
            self._propose(new, now)

    def _consume(self, d: HumanDecision, action: Action, now: datetime, *,
                 order: str | None = None, spec: str | None = None) -> dict[str, object]:
        preview = self._preview if action in (Action.ARM, Action.EXECUTE) else None
        self._ledger.consume(d, action=action, ticket=self._ticket, now=now, preview=preview,
                             order_id=order, spec_digest=spec)
        return {"decision": d.model_dump(mode="json")}

    def arm(self, spec: TriggerSpec, decision: HumanDecision, now: datetime) -> None:
        """Valida a condição antes de consumir a autorização específica."""
        self._require(T.DRAFT)
        trigger = Trigger(spec)
        trigger.arm(self._book, now)
        auth = self._consume(decision, Action.ARM, now, spec=spec_digest(spec))
        self._move(E.ARM, now, **auth)
        self._trigger = trigger

    def disarm(self, decision: HumanDecision, now: datetime) -> None:
        """Encerra a vigília por decisão humana."""
        self._require(T.ARMED)
        assert self._trigger is not None
        auth = self._consume(decision, Action.DISARM, now)
        self._trigger.disarm()
        self._move(E.DENY, now, **auth)

    def discard(self, decision: HumanDecision, now: datetime) -> None:
        """Descarta uma proposta ou aviso disparado."""
        self._require(T.DRAFT, T.TRIGGERED)
        self._move(E.DENY, now, **self._consume(decision, Action.DISCARD, now))

    def _market_block(self, plan: LegPlan, now: datetime) -> str | None:
        result = assess(plan.draft.legs, self._book, now, self._config)
        return ", ".join(result.reasons) if result.level == "BLOCKED" else None

    def confirm(self, decision: HumanDecision, now: datetime) -> None:
        """Confere estado, conta, prazos, mercado, limites e por último a decisão."""
        plan = self._require(T.DRAFT, T.TRIGGERED)
        if self._paused:
            raise EngineRefusal("boleta pausada")
        if self._halts.blocked(self._account):
            raise EngineRefusal("conta em estado incerto")
        check_deadlines(plan.draft, now, self._venue)
        if reason := self._market_block(plan, now):
            raise EngineRefusal(reason)
        if not within_signed_limits(plan.draft, (), plan.legs[0], known_costs=_ZERO):
            raise EngineRefusal("limites assinados")
        self._reservations.admissible(plan, ticket=self._ticket)
        auth = self._consume(decision, Action.EXECUTE, now)
        self._reservations.admit(plan, ticket=self._ticket)
        self._move(E.CONFIRM, now, **auth)
        self._move(E.START, now)
        self._drive(now)

    def _available(self, plan: LegPlan, leg: Leg) -> int:
        return self._reservations.available(plan, leg, ticket=self._ticket)

    def _rejected(self, leg: Leg) -> bool:
        return any(o.leg == leg and o.state == O.REJECTED for o in self._orders.values())

    def _destination(self, plan: LegPlan, now: datetime) -> T:
        if any(o.state in _LIVE for o in self._orders.values()):
            return T.WORKING
        if all(sum(f.quantity for f in self._fills if f.symbol == leg.symbol) == leg.quantity
               for leg in plan.legs):
            return T.COMPLETED
        if not self._cancelled and _send_window_open(plan.draft, now) and any(
                self._available(plan, leg) > 0 for leg in plan.legs if leg.side is Side.SELL
                and not self._rejected(leg)):
            return T.WORKING
        return T.STOPPED

    def _drive(self, now: datetime) -> None:
        if self._state != T.WORKING:
            return
        plan = self._require(T.WORKING)
        for leg in plan.legs:
            if (self._state != T.WORKING or self._paused or self._halts.blocked(self._account)
                    or self._cancelled or not _send_window_open(plan.draft, now)
                    or self._market_block(plan, now)):
                break
            previous = sum(o.leg.symbol == leg.symbol for o in self._orders.values())
            if self._rejected(leg) or (leg.side is Side.BUY and previous):
                continue
            quantity = leg.quantity if leg.side is Side.BUY else self._available(plan, leg)
            if not quantity:
                continue
            next_leg = leg.model_copy(update={"quantity": quantity})
            if not within_signed_limits(plan.draft, tuple(self._fills), next_leg,
                                        known_costs=_ZERO):
                self._move(E.STOP, now)
                return
            oid = f"{self._ticket}:{leg.symbol}:{previous + 1}"
            req = VenueOrder(order_id=oid, symbol=leg.symbol, side=leg.side, quantity=quantity,
                             limit_price=leg.limit_price, lot_size=leg.lot_size,
                             valid_until=plan.draft.order_validity)
            if leg.side is Side.SELL:
                self._reservations.reserve(plan, leg, oid, quantity, ticket=self._ticket)
            self._orders[oid] = _Order(req, leg)
            self._apply(self._venue.submit(req, now))
        if self._state == T.WORKING:
            dest = self._destination(plan, now)
            if dest != T.WORKING:
                self._move(E.COMPLETE if dest == T.COMPLETED else E.STOP, now)

    def _apply(self, r: VenueReport) -> None:
        order = self._orders[r.order_id]
        dest = transition(order.state, r.event)
        assert isinstance(dest, O) and self._plan is not None
        data: dict[str, object] = {"order_id": r.order_id, "state": dest.value}
        fill = None
        if r.event in (E.VENUE_FILL, E.VENUE_PARTIAL):
            assert r.quantity is not None and r.price is not None
            key = f"{r.order_id}#{order.executions + 1}"
            fill = Fill(execution=key, symbol=order.leg.symbol, side=order.leg.side,
                        quantity=r.quantity, price=r.price)
            order.executions += 1
            order.filled += r.quantity
            self._fills.append(fill)
            data.update(execution=key, price=str(r.price), quantity=r.quantity)
        if order.state == O.PENDING_SEND:
            data["request"] = order.request.model_dump(mode="json")
        order.state = dest
        self._record(r.event, r.ts, **data)
        self._account_report(order, r.ts, fill)
        if dest == O.UNCERTAIN:
            self._halts.hold(self._account, r.order_id)
            self._move(E.UNCERTAIN, r.ts)

    def _account_report(self, order: _Order, now: datetime, fill: Fill | None = None) -> None:
        oid = order.request.order_id
        try:
            if fill is not None:
                if order.leg.side is Side.BUY:
                    assert self._plan is not None
                    self._reservations.confirm_buy(self._plan, order.leg, fill.execution,
                                                   fill.quantity, ticket=self._ticket)
                else:
                    self._reservations.confirm_sale(
                        self._account, oid, fill.execution, fill.quantity)
            if order.state in (O.FILLED, O.CANCELLED, O.EXPIRED, O.REJECTED):
                if order.leg.side is Side.BUY:
                    self._reservations.settle_buy(self._account, self._ticket, order.leg.symbol)
                else:
                    self._release(order)
        except SequenceRefusal:
            self._record(E.DIVERGENCE, now, order_id=oid)
            self._halts.hold(self._account, "divergence")

    def _release(self, order: _Order) -> None:
        balance = order.request.quantity - order.filled
        if order.leg.side is Side.SELL and balance:
            self._reservations.confirm_release(self._account, order.request.order_id, balance)

    def on_reports(self, reports: Sequence[VenueReport], now: datetime) -> None:
        """Aplica o lote antes de decidir qualquer envio adicional."""
        for r in reports:
            order = self._orders.get(r.order_id)
            if order is None:
                raise EngineRefusal("ordem desconhecida")
            if order.state == O.UNCERTAIN:
                order.pending.append(r)
            else:
                self._apply(r)
        self._drive(now)

    def on_market(self, event: ReplayEvent) -> None:
        """Avalia um aviso ou a possibilidade de novo envio pela versão confirmada."""
        if self._state == T.ARMED:
            assert self._trigger is not None
            outcome = self._trigger.on_event(event, self._book)
            if outcome != Outcome.NONE:
                self._move(E.TRIGGER if outcome == Outcome.FIRED else E.EXPIRE, event.ts)
        else:
            self._drive(event.ts)

    def cancel(self, order_id: str, decision: HumanDecision, now: datetime) -> None:
        """Registra pedido humano mesmo com trava de mercado ou de conta."""
        order = self._orders.get(order_id)
        if order is None or order.state not in (O.LIVE, O.PARTIAL):
            raise EngineRefusal("ordem não cancelável")
        auth = self._consume(decision, Action.CANCEL_ORDER, now, order=order_id)
        state = transition(order.state, E.REQUEST_CANCEL)
        assert isinstance(state, O)
        order.state = state
        self._record(E.REQUEST_CANCEL, now, order_id=order_id, **auth)
        self._venue.request_cancel(order_id, now)
        self._cancelled = True

    def pause(self, now: datetime) -> None:
        """Pausa novos envios preservando ordens e reservas."""
        self._record(E.PAUSE, now)
        self._paused = True

    def resume(self, decision: HumanDecision, now: datetime) -> None:
        """Revalida os envios após a retomada humana."""
        if any(o.state == O.UNCERTAIN for o in self._orders.values()):
            raise EngineRefusal("conciliação pendente")
        self._record(E.RESUME, now, **self._consume(decision, Action.RESUME, now))
        self._paused = False
        self._drive(now)

    def reconcile(self, order_id: str, now: datetime) -> None:
        """Confere toda a fita pendente contra poll antes de alterar recibo e saldos."""
        plan = self._require(T.UNCERTAIN)
        order = self._orders.get(order_id)
        if order is None or order.state != O.UNCERTAIN:
            raise EngineRefusal("ordem não está incerta")
        snap = self._venue.poll(order_id)
        resolved = O.REJECTED if snap is None else O.LIVE
        simulated, filled = resolved, order.filled
        for r in order.pending:
            if snap is None:
                raise EngineRefusal("poll sem ordem para execução pendente")
            try:
                next_state = transition(simulated, r.event)
            except InvalidTransition as exc:
                raise EngineRefusal("fita pendente inconsistente com poll") from exc
            assert isinstance(next_state, O)
            simulated, filled = next_state, filled + (r.quantity or 0)
        if snap is not None and (simulated != snap.state or filled != snap.filled):
            raise EngineRefusal("poll diverge dos relatórios")
        state = reconcile(order.state, resolved, evidence="poll")
        assert isinstance(state, O)
        order.state = state
        self._record(E.RECONCILE, now, order_id=order_id, state=resolved.value, evidence="poll")
        if snap is None:
            self._account_report(order, now)
        for r in order.pending:
            self._apply(r)
        order.pending.clear()
        self._halts.release(self._account, order_id)
        if not any(o.state == O.UNCERTAIN for o in self._orders.values()):
            dest = self._destination(plan, now)
            state_ticket = reconcile(self._state, dest, evidence="poll")
            assert isinstance(state_ticket, T)
            self._record(E.RECONCILE, now, state=dest.value, evidence="poll")
            self._set_state(state_ticket)
            if dest == T.WORKING:
                self.pause(now)
