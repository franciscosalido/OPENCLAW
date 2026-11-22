"""Oráculos de emissão, precedência, vínculo e consumo único em D0."""
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.derivatives.ticket.gate import Action, DecisionLedger, DecisionRefusal, issue
from backend.derivatives.ticket.models import EditableField, FieldRef, Preview, apply_human_edit
from tests.unit.derivatives.ticket.test_models import TIME, PRICE
from tests.unit.derivatives.ticket.test_sequencing import BUY, SELL, draft

T = draft(BUY, SELL)
P = Preview.from_draft(T, partial_exposure=Decimal("10"))
LIMIT = TIME + timedelta(minutes=5)
BASE = dict(ticket="T1", nonce="n1", issued_at=TIME, expires_at=LIMIT)
USE = dict(action=Action.EXECUTE, ticket="T1", now=TIME+timedelta(minutes=1), preview=P)
Q = FieldRef(EditableField.QUANTITY, 0)
P2 = Preview.from_draft(apply_human_edit(T, PRICE, Decimal(".99")), partial_exposure=Decimal("10"))
P3 = Preview.from_draft(apply_human_edit(apply_human_edit(T,Q,20),Q,10),
                        partial_exposure=Decimal("10"))


@pytest.mark.parametrize(("action","options","reason"), [
    ("EXECUTE",dict(ticket="", preview=P),"identidade ausente"),
    ("EXECUTE",dict(nonce="", preview=P),"identidade ausente"),
    ("EXECUTE",dict(issued_at=TIME.replace(tzinfo=None), preview=P),"tempo inválido"),
    ("EXECUTE",dict(expires_at=LIMIT.replace(tzinfo=None), preview=P),"tempo inválido"),
    ("EXECUTE",dict(expires_at=TIME, preview=P),"tempo inválido"),
    ("EXECUTE",dict(expires_at=TIME-timedelta(seconds=1), preview=P),"tempo inválido"),
    ("EXECUTE",{},"vínculo ausente"), ("ARM",dict(spec_digest="aaa"),"vínculo ausente"),
    ("ARM",dict(preview=P),"vínculo ausente"), ("CANCEL_ORDER",{},"vínculo ausente"),
    ("RESUME",dict(preview=P),"vínculo indevido"), ("DISARM",dict(order_id="o1"),"vínculo indevido"),
    ("DISCARD",dict(spec_digest="aaa"),"vínculo indevido"),
    ("EXECUTE",dict(preview=P,order_id="o1"),"vínculo indevido"),
    ("EXECUTE",dict(preview=P,spec_digest="aaa"),"vínculo indevido"),
    ("ARM",dict(preview=P,spec_digest="aaa",order_id="o1"),"vínculo indevido"),
    ("CANCEL_ORDER",dict(preview=P,order_id="o1"),"vínculo indevido"),
], ids="I1-ticket I1-nonce I2-issued I2-expires I3-equal I3-before I4 I5-preview I5-spec I6 I7-resume I7-disarm I7-discard I8-order I8-spec arm-order cancel-preview".split())
def test_issue_refuses(action: str, options: dict, reason: str) -> None:
    """As recusas de emissão têm motivo explícito."""
    with pytest.raises(DecisionRefusal, match=reason):
        issue(Action(action), **(BASE | options))


@pytest.mark.parametrize(("opts","reason"), [
    ({},None), (dict(now=LIMIT),None), (dict(now=LIMIT+timedelta(microseconds=1)),"decisão vencida"),
    (dict(now=TIME-timedelta(seconds=1)),"decisão ainda não válida"), (dict(now=TIME),None),
    (dict(preview=P2),"resumo divergente"), (dict(preview=P3),"versão divergente"),
    (dict(ticket="T2"),"boleta divergente"), (dict(action=Action.CANCEL_ORDER),"ação divergente"),
    (dict(ticket="T2", now=LIMIT+timedelta(seconds=1)),"boleta divergente"),
], ids="K1 K3 K3b K4 K4b K5 K6 K7 K8 K12".split())
def test_consume(opts: dict, reason: str | None) -> None:
    """A ida e volta da quantidade recupera o resumo da versão 1."""
    assert (P.version,P2.version,P3.version)==(1,2,3)
    assert P.digest != P2.digest and P.digest == P3.digest
    ledger=DecisionLedger()
    decision=issue(Action.EXECUTE, **BASE, preview=P)
    if reason:
        with pytest.raises(DecisionRefusal, match=reason):
            ledger.consume(decision, **(USE | opts))
    else:
        assert ledger.consume(decision, **(USE | opts)) is None


def test_k2_k11_nonce_is_global_to_the_ledger() -> None:
    """Repetir a decisão ou reutilizar o nonce em outra ação e boleta recusa."""
    ledger=DecisionLedger()
    one=issue(Action.EXECUTE, **BASE, preview=P)
    ledger.consume(one, **USE)
    with pytest.raises(DecisionRefusal, match="decisão já usada"):
        ledger.consume(one, **USE)
    two=issue(Action.RESUME, **(BASE | dict(ticket="T2")))
    with pytest.raises(DecisionRefusal, match="decisão já usada"):
        ledger.consume(two, action=Action.RESUME, ticket="T2", now=TIME)


def test_k9_and_k9b_failed_order_binding_leaves_nonce_available() -> None:
    """A primeira recusa preserva a decisão de cancelamento de o1."""
    ledger=DecisionLedger()
    decision=issue(Action.CANCEL_ORDER, **BASE, order_id="o1")
    args=dict(action=Action.CANCEL_ORDER,ticket="T1",now=TIME)
    with pytest.raises(DecisionRefusal, match="ordem divergente"):
        ledger.consume(decision, **args, order_id="o2")
    ledger.consume(decision, **args, order_id="o1")


def test_k10_spec_binding() -> None:
    """A decisão de armar é específica à condição apresentada."""
    decision=issue(Action.ARM, **BASE, preview=P, spec_digest="aaa")
    ledger=DecisionLedger()
    with pytest.raises(DecisionRefusal, match="gatilho divergente"):
        ledger.consume(decision, **(USE | dict(action=Action.ARM,spec_digest="bbb")))
    ledger.consume(decision, **(USE | dict(action=Action.ARM,spec_digest="aaa")))


def test_immutable_decision() -> None:
    """Decisão emitida bloqueia alteração posterior e campos excedentes."""
    decision=issue(Action.DISCARD, **BASE)
    with pytest.raises(ValidationError):
        decision.ticket="T2"
    with pytest.raises(ValidationError):
        type(decision).model_validate(dict(decision) | {"unknown":1})
