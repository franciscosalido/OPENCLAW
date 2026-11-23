"""Provas do modelo D0, da versão editada e do conteúdo autorizável."""
import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256

import pytest
from pydantic import ValidationError

from backend.derivatives.ticket.digest import canonical_bytes, digest
from backend.derivatives.ticket.models import (
    EditableField, Environment, FieldRef, Leg, MarketSuggestion, Preview, Side, TicketDraft,
    apply_human_edit, apply_market_refresh, unlock,
)

D = Decimal
TIME = datetime(2026, 11, 21, 14, tzinfo=UTC)
PRICE = FieldRef(field=EditableField.LIMIT_PRICE, leg_index=0)
OTHER = FieldRef(field=EditableField.LIMIT_PRICE, leg_index=1)


def leg(symbol: str, side: Side = Side.BUY) -> Leg:
    """Cria série sintética com lote de dez."""
    return Leg(symbol=symbol, side=side, quantity=20, lot_size=10, limit_price=D("1.20"))


def draft() -> TicketDraft:
    """Fornece um rascunho com duas pernas distintas."""
    return TicketDraft(legs=(leg("SYNA"), leg("SYNB", Side.SELL)), net_limit=D("-2.50"),
                       gross_cap=D("24"), send_deadline=TIME,
                       order_validity=TIME + timedelta(days=1),
                       quote_snapshot_id="q0")


def preview(source: TicketDraft | None = None) -> Preview:
    """Associa uma exposição declarada à versão do rascunho."""
    return Preview.from_draft(source or draft(), partial_exposure=D("24"))


def test_canonical_contract() -> None:
    """Confere bytes por um documento independente, incluindo ordem das pernas e horários."""
    p = preview()
    expected = {
        "environment": "SIMULATED",
        "legs": [{"symbol": symbol, "side": side, "quantity": 20, "limit_price": "1.2"}
                 for symbol, side in [("SYNA", "BUY"), ("SYNB", "SELL")]],
        "net_limit": "-2.5", "gross_cap": "24", "partial_exposure": "24",
        "send_deadline": "2026-11-21T14:00:00+00:00", "order_validity": "2026-11-22T14:00:00+00:00",
        "quote_snapshot_id": "q0",
    }
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    assert canonical_bytes(p) == encoded
    assert p.digest == digest(p) == sha256(encoded).hexdigest()
    values = dict(reversed(list(dict(draft()).items())))
    values.update(net_limit=D("-2.50000"),
                  send_deadline=TIME.astimezone(timezone(timedelta(hours=2))))
    assert preview(TicketDraft.model_validate(values)).digest == p.digest


@pytest.mark.parametrize(("field", "value"), [
    ("net_limit", D("-2.49")), ("gross_cap", D("25")), ("partial_exposure", D("23")),
    ("send_deadline", TIME + timedelta(seconds=1)), ("order_validity", TIME + timedelta(days=2)),
    ("quote_snapshot_id", "q1"),
])
def test_signed_ticket_fields(field: str, value: object) -> None:
    """Cada valor autorizável participa do conteúdo assinado."""
    p = preview()
    assert Preview.model_validate(dict(p) | {field: value}).digest != p.digest


@pytest.mark.parametrize(("field", "value"), [
    ("symbol", "SYNC"), ("side", Side.SELL), ("quantity", 30), ("limit_price", D("1.21")),
])
def test_signed_leg_fields(field: str, value: object) -> None:
    """Cada campo da perna e a ordem econômica participam do resumo."""
    p = preview()
    changed = Leg.model_validate(dict(p.legs[0]) | {field: value})
    assert Preview.model_validate(dict(p) | {"legs": (changed, p.legs[1])}).digest != p.digest
    assert Preview.model_validate(dict(p) | {"legs": p.legs[::-1]}).digest != p.digest


def test_decimal_precision_and_zero() -> None:
    """Precisão ambiente não arredonda quantias nem distingue zero negativo."""
    with localcontext() as ctx:
        ctx.prec = 3
        p = Preview.model_validate(dict(preview()) | {"gross_cap": D("12345678901234567890.1200")})
        assert json.loads(canonical_bytes(p))["gross_cap"] == "12345678901234567890.12"
        for zero in ("0", "-0.00"):
            assert json.loads(canonical_bytes(Preview.model_validate(dict(p) | {
                "net_limit": D(zero)})))["net_limit"] == "0"


def test_refresh_locks_and_version() -> None:
    """Atualização de várias pernas respeita travas individuais e avança uma só versão."""
    original = draft()
    edited = apply_human_edit(original, PRICE, D("2.00"))
    assert edited.version == original.version + 1 and edited.locked == {PRICE}
    for suggestions in ({}, {PRICE: D("3")}, {OTHER: D("1.2000")}):
        assert apply_market_refresh(edited, MarketSuggestion("new", suggestions)) is edited
    updated = apply_market_refresh(edited, MarketSuggestion("q1", {PRICE: D("3"), OTHER: D("4")}))
    assert [x.limit_price for x in updated.legs] == [D("2"), D("4")]
    assert updated.version == edited.version + 1 and updated.quote_snapshot_id == "q1"
    assert updated.locked == {PRICE} and edited.quote_snapshot_id == "q0"
    unlocked = unlock(updated, PRICE)
    assert unlocked.version == updated.version
    assert preview(unlocked).digest == preview(updated).digest
    refreshed = apply_market_refresh(unlocked, MarketSuggestion("q2", {PRICE: D("3")}))
    assert refreshed.legs[0].limit_price == 3


def test_same_content_after_two_edits_has_new_version() -> None:
    """O conteúdo ABA pode repetir; a versão distingue as duas propostas."""
    first = draft()
    second = apply_human_edit(apply_human_edit(first, PRICE, D("2")), PRICE, D("1.20"))
    assert second.version == first.version + 2 and preview(first).digest == preview(second).digest


@pytest.mark.parametrize(("field", "value"), [
    ("limit_price", .1), ("limit_price", "1"), ("limit_price", D("1.001")),
    ("limit_price", D("NaN")), ("limit_price", D("Infinity")), ("limit_price", D("-1")),
    ("quantity", True), ("quantity", 15), ("lot_size", 0), ("quantity", 0),
])
def test_leg_rejects_invalid_inputs(field: str, value: object) -> None:
    """Valores de dinheiro e quantidade não sofrem coerção ou arredondamento."""
    with pytest.raises(ValidationError):
        Leg.model_validate(dict(leg("SYNA")) | {field: value})


@pytest.mark.parametrize(("field", "value"), [
    ("legs", ()), ("legs", (leg("SYNA"),) * 2), ("legs", tuple(leg(str(i)) for i in range(5))),
    ("environment", "REAL"), ("gross_cap", 2.), ("net_limit", 1.), ("locked", frozenset({FieldRef(
        field=EditableField.SIDE, leg_index=3)})), ("send_deadline", TIME.replace(tzinfo=None)),
    ("extra", 1),
])
def test_invalid_draft(field: str, value: object) -> None:
    """Validação integral na construção do rascunho."""
    with pytest.raises(ValidationError):
        TicketDraft.model_validate(dict(draft()) | {field: value})


def test_edit_and_preview_validate_nested_values() -> None:
    """Edições inválidas e cópias Pydantic fabricadas não chegam à assinatura."""
    with pytest.raises(ValidationError):
        apply_human_edit(draft(), PRICE, 1.)
    with pytest.raises(ValidationError):
        preview(draft().model_copy(update={"legs": (leg("S").model_copy(update={"quantity": 1}),)}))
    with pytest.raises(ValidationError):
        Preview.model_validate(dict(preview()) | {"partial_exposure": 1.})
    assert {member.value for member in Environment} == {"SIMULATED"}


def test_json_money_requires_decimal_text() -> None:
    """O caminho JSON rejeita número de ponto flutuante e aceita texto exato."""
    fields = {"symbol": "SYN", "side": "BUY", "quantity": 1, "lot_size": 1}
    exact = Leg.model_validate_json(json.dumps(fields | {"limit_price": "0.10"}))
    assert exact.limit_price == D(".1")
    with pytest.raises(ValidationError):
        Leg.model_validate_json(json.dumps(fields | {"limit_price": .1}))


def test_large_equivalent_decimals_have_compact_encoding() -> None:
    """Representações equivalentes de grandes potências conservam os mesmos bytes."""
    for amount in ("1E100000", "100E99998"):
        data = Preview.model_validate(dict(preview()) | {"gross_cap": D(amount)})
        assert json.loads(canonical_bytes(data))["gross_cap"] == "1E+100000"
    debit = Preview.model_validate(dict(preview()) | {"net_limit": D("1E100000")})
    credit = Preview.model_validate(dict(preview()) | {"net_limit": D("-1E100000")})
    assert json.loads(canonical_bytes(credit))["net_limit"] == "-1E+100000"
    assert credit.digest != debit.digest


@pytest.mark.parametrize(("ref", "value", "replacement"), [
    (FieldRef(EditableField.SYMBOL, 0), "SYNC", "SYNX"),
    (FieldRef(EditableField.SIDE, 0), Side.SELL, Side.BUY),
    (FieldRef(EditableField.QUANTITY, 0), 40, 30),
    (FieldRef(EditableField.NET_LIMIT), D("0"), D("1")),
    (FieldRef(EditableField.SEND_DEADLINE), TIME - timedelta(minutes=1), TIME),
    (FieldRef(EditableField.ORDER_VALIDITY), TIME + timedelta(hours=2), TIME),
])
def test_each_operational_field_stays_locked(ref: FieldRef, value: object,
                                            replacement: object) -> None:
    """A trava é endereçada e a foto só avança quando uma sugestão é adotada."""
    edited = apply_human_edit(draft(), ref, value)
    assert ref in edited.locked and edited.version == 2
    assert apply_market_refresh(edited, MarketSuggestion("q1", {ref: replacement})) is edited
    update = apply_market_refresh(unlock(edited, ref), MarketSuggestion("q2", {ref: replacement}))
    assert update.version == 3 and update.quote_snapshot_id == "q2"


def test_refresh_is_atomic_and_revalidates_the_whole_draft() -> None:
    """A troca simultânea de séries é válida; duplicação final é recusada."""
    first, second = (FieldRef(EditableField.SYMBOL, i) for i in (0, 1))
    original = draft()
    with pytest.raises(ValidationError):
        apply_market_refresh(original, MarketSuggestion("q1", {first: "synb"}))
    changes = {first: "SYNB", second: "SYNA"}
    changed = apply_market_refresh(original, MarketSuggestion("q1", changes))
    assert tuple(x.symbol for x in changed.legs) == ("SYNB", "SYNA")
    assert changed.version == 2 and original.legs[0].symbol == "SYNA"


def test_version_digest_and_environment_cannot_be_supplied_as_signed_overrides() -> None:
    """A versão fica fora do hash; a prévia recusa ambiente e digest forjados."""
    p = preview()
    assert Preview.model_validate(dict(p) | {"version": 500}).digest == p.digest
    for overrides in ({"environment": "REAL"}, {"digest": "0" * 64}):
        with pytest.raises(ValidationError):
            Preview.model_validate(dict(p) | overrides)
    with pytest.raises(ValidationError):
        digest(p.model_copy(update={"net_limit": .3}))


def test_lot_validates_quantity_without_changing_signed_content() -> None:
    """O SDD assina unidades e limite por perna. O lote valida as unidades."""
    p = preview()
    valid = Leg.model_validate(dict(p.legs[0]) | {"lot_size": 5})
    other = Preview.model_validate(dict(p) | {"legs": (valid, p.legs[1])})
    assert other.digest == p.digest
    with pytest.raises(ValidationError):
        Leg.model_validate(dict(valid) | {"lot_size": 3})


def test_w1_coverage_grant_and_ticket_validation() -> None:
    """Valida normalização, imutabilidade, identidade e cardinalidade das autorizações."""
    from backend.derivatives.ticket.models import CoverageGrant

    grant = CoverageGrant(series="a", origin="T1", quantity=4)
    assert (grant.series, grant.origin, grant.quantity) == ("A", "T1", 4)
    with pytest.raises(ValidationError):
        grant.quantity = 2
    for change in ({"origin": "T 1"}, {"origin": "T1:x"}, {"origin": ""}, {"series": ""},
                   {"quantity": 0}, {"quantity": True}):
        with pytest.raises(ValidationError):
            CoverageGrant.model_validate(dict(grant) | change)
    assert draft().coverage == ()
    with pytest.raises(ValidationError, match="autorização de cobertura duplicada"):
        duplicate = dict(grant) | {"quantity": 2}
        TicketDraft.model_validate(dict(draft()) | {"coverage": (grant, duplicate)})
    grants = tuple(CoverageGrant(series="A", origin=f"T{i}", quantity=1) for i in range(5))
    accepted = TicketDraft.model_validate(dict(draft()) | {"coverage": grants[:4]})
    assert accepted.coverage == grants[:4]
    with pytest.raises(ValidationError):
        TicketDraft.model_validate(dict(draft()) | {"coverage": grants})


def test_w2_receipt_and_signed_coverage_use_canonical_order() -> None:
    """O recibo e os bytes assinados preservam a mesma prioridade nas duas permutações."""
    from backend.derivatives.ticket.receipt import Receipt
    from tests.unit.derivatives.ticket.test_sequencing import BUY, SELL, draft as reference

    base = reference(BUY, SELL)
    def signed(*grants: dict[str, object]) -> Preview:
        ticket = TicketDraft.model_validate(dict(base) | {"coverage": grants})
        return Preview.from_draft(ticket, partial_exposure=D("10"))

    empty = Preview.from_draft(base, partial_exposure=D("10"))
    assert empty.digest == "d258890d354ab0aabd95f2ae8e4fee95aa1f05e5afd102082d8f8141bd27c0af"
    assert "coverage" not in empty.model_dump() and b'"coverage"' not in canonical_bytes(empty)
    g9 = {"series": "A", "origin": "T9", "quantity": 2}
    g1 = {"series": "A", "origin": "T1", "quantity": 4}
    authorized = signed(g9, g1)
    assert authorized.digest == signed(g1, g9).digest == (
        "f61d4551b8be2caec9f54774d536acf5fbc2655578555dc4843862de3e86a84e")
    expected = (b'"coverage":[{"origin":"T1","quantity":4,"series":"A"},'
                b'{"origin":"T9","quantity":2,"series":"A"}]')
    assert expected in canonical_bytes(authorized)
    assert signed(g1 | {"quantity": 5}, g9).digest != authorized.digest
    receipt = Receipt()
    plain = receipt.append_preview(TIME, empty)
    assert "coverage" not in json.loads(plain.payload)["preview"]
    for p in (authorized, signed(g1, g9)):
        covered = receipt.append_preview(TIME, p)
        assert json.loads(covered.payload)["preview"]["coverage"] == [g1, g9]
        assert covered.read_preview() == p and receipt.verify()


def test_k1_coverage_digest_orders_series_before_origin() -> None:
    from tests.unit.derivatives.ticket.test_sequencing import BUY, SELL, authorized, draft as base

    first, second = ("B", "T1", 1), ("A", "T9", 2)
    fragment = (b'"coverage":[{"origin":"T9","quantity":2,"series":"A"},'
                b'{"origin":"T1","quantity":1,"series":"B"}]')
    for grants in ((first, second), (second, first)):
        p = Preview.from_draft(authorized(base(BUY, SELL), *grants), partial_exposure=D("10"))
        assert p.digest == "364d378948c544bc1afbe75e4f6b7d50b3c9f7e7fd86386f919adfc9971a601e"
        assert fragment in canonical_bytes(p)


def test_n1_one_grant_order_from_draft_to_receipt() -> None:
    """Permutações e caixa da série preservam o modelo, o digest histórico e o recibo."""
    from backend.derivatives.ticket.receipt import Receipt
    from tests.unit.derivatives.ticket.test_sequencing import BUY, SELL, authorized, draft as base

    ticket = base(BUY, SELL)
    a1, a9, b1 = ("A", "T1", 4), ("A", "T9", 2), ("B", "T1", 1)
    for inputs, expected, expected_digest in (
        ((a9, a1), (a1, a9), "f61d4551b8be2caec9f54774d536acf5fbc2655578555dc4843862de3e86a84e"),
        ((b1, a9), (a9, b1), "364d378948c544bc1afbe75e4f6b7d50b3c9f7e7fd86386f919adfc9971a601e"),
    ):
        reference = authorized(ticket, *expected)
        canonical = Preview.from_draft(reference, partial_exposure=D("10"))
        for pair in (inputs, inputs[::-1]):
            proposal = authorized(ticket, *pair)
            assert proposal == reference
            shown = Preview.from_draft(proposal, partial_exposure=D("10"))
            assert shown == canonical and shown.digest == expected_digest
            raw = canonical.model_dump(mode="json", exclude={"digest"})
            raw["coverage"] = [{"series": s, "origin": o, "quantity": q} for s, o, q in pair]
            assert Preview.model_validate_json(json.dumps(raw)) == canonical
            assert tuple((g.series, g.origin, g.quantity) for g in shown.coverage) == expected
            receipt = Receipt()
            event = receipt.append_preview(TIME, shown)
            assert json.loads(event.payload)["preview"]["coverage"] == [
                {"series": series, "origin": origin, "quantity": qty}
                for series, origin, qty in expected]
            assert event.read_preview() == shown and receipt.verify()
    for series in ("b", "B"):
        proposal = authorized(ticket, (series, "T1", 1), ("a", "T9", 2))
        assert proposal == authorized(ticket, a9, b1)
