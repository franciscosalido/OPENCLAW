import json
from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from functools import partial
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from backend.derivatives.domain import series_terms
from backend.derivatives.domain.models import ExerciseStyle
from backend.derivatives.domain.series_terms import (
    AdjustmentEvidence,
    AdjustmentPolicy,
    RefusalCode,
    SeriesTerms,
    TermsRefusal,
)


def sample() -> dict[str, Any]:
    return dict(symbol="SYNX63", effective_on=date(2026, 1, 5), source="fixture A",
                strike=Decimal("1.234567890123456789012345678901234567890"),
                contract_size=37, quotation_form=1000, currency="BRL",
                exercise_style=ExerciseStyle.EUROPEAN, adjustment_policy=AdjustmentPolicy.UNKNOWN)


def evidence(policy: AdjustmentPolicy) -> dict[str, Any]:
    return dict(issuer="B3", document="fixture sintética, seção 2", version="rev1",
                published_on=date(2026, 1, 2), symbol="SYNX63",
                effective_on=date(2026, 1, 5), policy=policy)


def terms(policy: AdjustmentPolicy = AdjustmentPolicy.UNKNOWN) -> SeriesTerms:
    fields = sample()
    if policy is not AdjustmentPolicy.UNKNOWN:
        fields.update(adjustment_policy=policy, evidence=evidence(policy))
    return SeriesTerms(**fields)


def test_missing_contract_size() -> None:
    fields = sample()
    del fields["contract_size"]
    with pytest.raises(TermsRefusal) as refusal:
        SeriesTerms(**fields)
    assert refusal.value.code == "missing_contract_size"


@pytest.mark.parametrize("wire", [False, True], ids=["mapping", "json"])
@pytest.mark.parametrize("absent", ["omitted", "null"])
def test_ordered_refusals(wire: bool, absent: str) -> None:
    fields = terms().model_dump(mode="json" if wire else "python")
    keys = ["contract_size", "quotation_form", "exercise_style", "currency"]
    codes = ["missing_contract_size", "missing_quotation_form",
             "unknown_exercise_style", "unknown_currency"]
    for i, code in enumerate(codes):
        payload = fields.copy()
        for key in keys[i:]:
            if absent == "omitted":
                del payload[key]
            else:
                payload[key] = None
        with pytest.raises(TermsRefusal) as refusal:
            if wire:
                SeriesTerms.model_validate_json(json.dumps(payload))
            else:
                SeriesTerms.model_validate(MappingProxyType(payload))
        assert refusal.value.code == code


@pytest.mark.parametrize("wire", [False, True])
def test_unknown_style_refusal(wire: bool) -> None:
    fields = terms().model_dump(mode="json" if wire else "python")
    fields["exercise_style"] = "UNKNOWN" if wire else ExerciseStyle.UNKNOWN
    with pytest.raises(TermsRefusal) as refusal:
        if wire:
            SeriesTerms.model_validate_json(json.dumps(fields))
        else:
            SeriesTerms.model_validate(fields)
    assert refusal.value.code == "unknown_exercise_style"


@pytest.mark.parametrize(("field", "value"), [
    ("contract_size", 0), ("contract_size", -5), ("contract_size", True),
    ("contract_size", 37.0), ("contract_size", "37"), ("quotation_form", 0),
    ("quotation_form", 37), ("quotation_form", True), ("quotation_form", 1.0),
    ("quotation_form", "1000"), ("exercise_style", "?"), ("exercise_style", True),
    ("currency", "USD"), ("currency", ""), ("currency", True),
])
def test_present_invalid_terms_are_structural(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        SeriesTerms(**(sample() | {field: value}))


@pytest.mark.parametrize("factor", [1, 1000])
def test_independent_lot_and_effective_strike(factor: int) -> None:
    first = SeriesTerms(**(sample() | {"quotation_form": factor}))
    later = SeriesTerms(**(sample() | dict(effective_on=date(2026, 1, 6), strike=Decimal("176"),
                                          exercise_style=ExerciseStyle.AMERICAN)))
    assert (first.contract_size, first.quotation_form) == (37, factor)
    assert first.strike.as_tuple() == sample()["strike"].as_tuple()
    assert first.symbol == later.symbol and first.effective_on < later.effective_on
    assert later.strike == Decimal("176")
    assert first.adjustment_policy is AdjustmentPolicy.UNKNOWN


@pytest.mark.parametrize(("field", "value"), [
    ("strike", 1.1), ("strike", "1.1"), ("strike", 1), ("strike", Decimal("NaN")),
    ("strike", Decimal("Infinity")), ("strike", Decimal("-0")),
    ("source", "  "), ("symbol", ""), ("effective_on", None), ("effective_on", "2026-01-05"),
    ("adjustment_policy", "MAYBE"), ("adjustment_policy", "UNKNOWN"),
    ("exercise_style", "AMERICAN"),
])
def test_invalid_metadata(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        SeriesTerms(**(sample() | {field: value}))


@pytest.mark.parametrize("policy", [AdjustmentPolicy.PROTECTED, AdjustmentPolicy.UNPROTECTED])
def test_conclusive_policy_requires_matching_evidence(policy: AdjustmentPolicy) -> None:
    fields = sample() | dict(adjustment_policy=policy)
    with pytest.raises(ValidationError):
        SeriesTerms(**fields)
    doc = evidence(policy)
    accepted = SeriesTerms(**(fields | {"evidence": doc})).evidence
    assert accepted is not None and accepted.version == "rev1"
    other = (AdjustmentPolicy.UNPROTECTED if policy is AdjustmentPolicy.PROTECTED
             else AdjustmentPolicy.PROTECTED)
    patches: list[dict[str, object]] = [
        dict(issuer="vendor"), dict(version=" "), dict(document=""), dict(published_on=None),
        dict(effective_on=date(2025, 1, 5)), dict(symbol="SYNX65"),
        dict(policy=AdjustmentPolicy.UNKNOWN), dict(policy=other),
    ]
    for patch in patches:
        with pytest.raises(ValidationError):
            SeriesTerms(**(fields | {"evidence": doc | patch}))


@pytest.mark.parametrize(("original", "update", "error"), [
    (AdjustmentPolicy.UNKNOWN, {"adjustment_policy": AdjustmentPolicy.PROTECTED}, ValidationError),
    (AdjustmentPolicy.PROTECTED, {"adjustment_policy": AdjustmentPolicy.UNPROTECTED},
     ValidationError),
    (AdjustmentPolicy.UNKNOWN, {"contract_size": None}, TermsRefusal),
    (AdjustmentPolicy.UNKNOWN, {"contract_size": -5}, ValidationError),
    (AdjustmentPolicy.UNKNOWN, {"typo": 37}, ValidationError),
])
def test_b1_invalid_terms_copy(
    original: AdjustmentPolicy, update: Mapping[str, object], error: type[Exception],
) -> None:
    original_terms = terms(original)
    with pytest.raises(error):
        original_terms.model_copy(update=update)
    assert original_terms.adjustment_policy is original and original_terms.contract_size == 37


@pytest.mark.parametrize("deep", [False, True])
def test_b1_copy_contract(deep: bool) -> None:
    original = terms(AdjustmentPolicy.PROTECTED)
    doc = original.evidence
    assert doc is not None
    for model in [original, doc]:
        for copy in [model.model_copy(deep=deep), model.model_copy(update={}, deep=deep)]:
            assert copy == model and copy is not model
            if isinstance(copy, SeriesTerms):
                assert (copy.evidence is doc) is (not deep)
    revised = doc.model_copy(update={"version": " rev2 "}, deep=deep)
    changed = original.model_copy(update={"evidence": revised, "contract_size": 41}, deep=deep)
    assert changed.evidence is not None and changed.evidence.version == "rev2"
    assert changed.contract_size == 41 and original.contract_size == 37 and doc.version == "rev1"


@pytest.mark.parametrize("update", [{"issuer": "fixture"}, {"version": " "}, {"extra": True}])
def test_b1_invalid_evidence_copy(update: dict[str, object]) -> None:
    doc = AdjustmentEvidence.model_validate(evidence(AdjustmentPolicy.PROTECTED))
    with pytest.raises(ValidationError):
        doc.model_copy(update=update)


@pytest.mark.parametrize("via_copy", [False, True])
def test_b1_prebuilt_invalid_evidence(via_copy: bool) -> None:
    policy = AdjustmentPolicy.PROTECTED
    # Simula um produtor confiável que errou. A fronteira pública recebe a instância pronta.
    invalid = AdjustmentEvidence.model_construct(**(evidence(policy) | {"issuer": "fixture"}))
    patch = {"evidence": invalid, "adjustment_policy": policy}
    with pytest.raises(ValidationError) as exc:
        if via_copy:
            terms().model_copy(update=patch)
        else:
            SeriesTerms.model_validate(sample() | patch)
    assert ("evidence", "issuer") in {error["loc"] for error in exc.value.errors()}


def test_b1_deep_update_rechecks_the_whole_record() -> None:
    policy = AdjustmentPolicy.PROTECTED
    original = terms()
    patch = {"adjustment_policy": policy, "evidence": evidence(policy)}
    complete = original.model_copy(update=patch, deep=True)
    assert complete == terms(policy) and original.evidence is None
    with pytest.raises(ValidationError):
        complete.model_copy(update={"evidence": evidence(policy) | {"extra": 1}}, deep=True)


def test_b1_legacy_copy_checks_terms() -> None:
    original = terms()
    with pytest.warns(DeprecationWarning, match="model_copy"), pytest.raises(TermsRefusal):
        original.copy(update={"contract_size": None})
    with pytest.warns(DeprecationWarning, match="model_copy"), pytest.raises(ValidationError):
        original.copy(update={"adjustment_policy": AdjustmentPolicy.PROTECTED})
    with pytest.warns(DeprecationWarning, match="model_copy"):
        assert original.copy(update={"contract_size": 41}).contract_size == 41


def test_b1_legacy_copy_checks_evidence() -> None:
    doc = AdjustmentEvidence.model_validate(evidence(AdjustmentPolicy.PROTECTED))
    with pytest.warns(DeprecationWarning, match="model_copy"), pytest.raises(ValidationError):
        doc.copy(update={"issuer": "fixture"})
    with pytest.warns(DeprecationWarning, match="model_copy"):
        assert doc.copy(update={"version": " rev2 "}, deep=True).version == "rev2"


def test_b1_legacy_copy_cannot_drop_required_fields() -> None:
    original = terms()
    with (
        pytest.warns(DeprecationWarning, match="model_copy"),
        pytest.raises(ValueError, match="model_dump"),
    ):
        original.copy(exclude={"contract_size"})
    with (
        pytest.warns(DeprecationWarning, match="model_copy"),
        pytest.raises(ValueError, match="model_dump"),
    ):
        original.copy(include={"strike"})


def test_b2_policy_description_in_public_schema() -> None:
    schema = SeriesTerms.model_json_schema()["$defs"]["AdjustmentPolicy"]
    description = schema.get("description", "").casefold()
    for term in ("proventos", "indopc", "igp-m", "refer. protected"):
        assert term in description, f"JSON Schema sem {term!r}: {description!r}"


def test_b2_unsupported_fatcot_is_a_present_value() -> None:
    # O chamador já forneceu um fator. Uma recusa por ausência pediria o dado errado.
    with pytest.raises(ValidationError):
        SeriesTerms(**(sample() | {"quotation_form": 100}))


def test_b2_public_docstrings_and_width() -> None:
    public = (RefusalCode, TermsRefusal, AdjustmentPolicy, SeriesTerms.require_series_fields,
              SeriesTerms.require_decimal, SeriesTerms.require_applicable_evidence)
    assert all(obj.__doc__ and obj.__doc__.strip() for obj in public)
    lines = Path(series_terms.__file__).read_text().splitlines()
    assert all(len(line) <= 100 for line in lines)


@pytest.mark.parametrize("policy", list(AdjustmentPolicy))
def test_b3_json_round_trip(policy: AdjustmentPolicy) -> None:
    original = terms(policy)
    wire = original.model_dump_json()
    restored = SeriesTerms.model_validate_json(wire)
    assert restored == original
    assert restored.strike.as_tuple() == original.strike.as_tuple()
    assert restored.exercise_style is original.exercise_style
    assert restored.adjustment_policy is policy
    assert type(restored.effective_on) is date
    if original.evidence is not None:
        assert restored.evidence is not None and restored.evidence.policy is policy
        assert type(restored.evidence.published_on) is type(restored.evidence.effective_on) is date
        assert AdjustmentEvidence.model_validate_json(original.evidence.model_dump_json()) == (
            original.evidence
        )


def test_b3_python_and_json_dicts() -> None:
    original = terms(AdjustmentPolicy.PROTECTED)
    assert SeriesTerms.model_validate(original.model_dump()) == original
    with pytest.raises(ValidationError):
        SeriesTerms.model_validate(original.model_dump(mode="json"))


@pytest.mark.parametrize("strict", [None, False])
@pytest.mark.parametrize(("path", "value"), [
    ("effective_on", 1767571200), ("effective_on", "2026-02-30"),
    ("contract_size", True), ("contract_size", "37"), ("contract_size", 37.0),
    ("quotation_form", True), ("quotation_form", 1000.0), ("quotation_form", "1"),
    ("strike", 123), ("strike", 1.25), ("strike", False), ("strike", "typo"),
    ("strike", "NaN"), ("strike", "Infinity"), ("strike", "-0"),
    ("exercise_style", 1), ("adjustment_policy", True), ("adjustment_policy", "protected"),
    ("evidence.effective_on", True), ("evidence.published_on", "2026-01-01T00:00:00"),
    ("evidence.policy", 1), ("evidence.document", 1),
    ("source", 123), ("symbol", 123), ("currency", 1), ("evidence.issuer", 3),
    ("effective_on", "20260105"), ("evidence.effective_on", "20260105"),
    ("evidence.published_on", "20260102"),
])
def test_b3_invalid_json_field(path: str, value: object, strict: bool | None) -> None:
    data = terms(AdjustmentPolicy.PROTECTED).model_dump(mode="json")
    parts = path.split(".")
    target = data if len(parts) == 1 else data[parts[0]]
    target[parts[-1]] = value
    with pytest.raises(ValidationError) as exc:
        SeriesTerms.model_validate_json(json.dumps(data), strict=strict)
    assert tuple(parts) in {error["loc"] for error in exc.value.errors()}


def test_attributes_are_outside_the_public_input_boundary() -> None:
    for kwargs in [sample(), {k: v for k, v in sample().items() if k != "contract_size"}]:
        with pytest.raises(ValidationError):
            SeriesTerms.model_validate(SimpleNamespace(**kwargs), from_attributes=True)
    payload = evidence(AdjustmentPolicy.PROTECTED)
    with pytest.raises(ValidationError):
        AdjustmentEvidence.model_validate(SimpleNamespace(**payload), from_attributes=True)


def test_read_only_mappings() -> None:
    policy = AdjustmentPolicy.PROTECTED
    doc = MappingProxyType(evidence(policy))
    data = MappingProxyType(sample() | {"adjustment_policy": policy, "evidence": doc})
    assert SeriesTerms.model_validate(data) == terms(policy)


def test_future_publication_is_inapplicable() -> None:
    original = terms(AdjustmentPolicy.PROTECTED)
    doc = evidence(AdjustmentPolicy.PROTECTED)
    for day in [date(2026, 1, 2), original.effective_on]:
        assert original.model_copy(update={"evidence": doc | {"published_on": day}}).evidence
    with pytest.raises(ValidationError):
        SeriesTerms.model_validate(original.model_dump() | {
            "evidence": doc | {"published_on": date(2027, 1, 2)},
        })
    assert original.evidence is not None
    with pytest.raises(ValidationError):
        original.evidence.model_copy(update={"published_on": date(2027, 1, 2)})


def test_frozen_models_and_extra_fields() -> None:
    original = terms(AdjustmentPolicy.PROTECTED)
    doc = original.evidence
    assert doc is not None
    for model, key in [(original, "contract_size"), (doc, "version")]:
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(model, key, "changed")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(model).model_validate(model.model_dump() | {"typo": 1})


class _Envelope(BaseModel, strict=False):
    terms: SeriesTerms


class _Label(StrEnum):
    BRL = "BRL"
    B3 = "B3"


@pytest.mark.parametrize(("path", "value"), [
    ("contract_size", True), ("contract_size", "37"), ("contract_size", 37.0),
    ("quotation_form", True), ("quotation_form", "1000"), ("quotation_form", 1000.0),
    ("exercise_style", "EUROPEAN"), ("exercise_style", "UNKNOWN"),
    ("effective_on", "2026-01-05"), ("effective_on", datetime(2026, 1, 5)),
    ("adjustment_policy", "PROTECTED"), ("evidence.policy", "PROTECTED"),
    ("evidence.published_on", 1767312000), ("evidence.effective_on", "2026-01-05"),
    ("strike", "176.00"), ("strike", 176), ("strike", 176.0),
    ("symbol", b"SYNX63"), ("source", bytearray(b"fixture")), ("currency", _Label.BRL),
    ("evidence.symbol", b"SYNX63"), ("evidence.document", b"fixture"),
    ("evidence.version", b"rev1"), ("evidence.issuer", _Label.B3),
    ("evidence", [("policy", "PROTECTED")]),
])
@pytest.mark.parametrize(("validate", "prefix"), [
    pytest.param(partial(SeriesTerms.model_validate, strict=False), (), id="model"),
    pytest.param(partial(TypeAdapter(SeriesTerms).validate_python, strict=False), (), id="adapter"),
    pytest.param(_Envelope.model_validate, ("terms",), id="lax-container"),
    pytest.param(partial(_Envelope.model_validate, strict=False), ("terms",), id="container-call"),
])
def test_s1_lax_python_field(
    path: str, value: object, validate: Callable[[object], object], prefix: tuple[str, ...],
) -> None:
    data = terms(AdjustmentPolicy.PROTECTED).model_dump()
    parts = path.split(".")
    target = data if len(parts) == 1 else data["evidence"]
    target[parts[-1]] = value
    with pytest.raises(ValidationError) as exc:
        validate({"terms": data} if prefix else data)
    assert [e["loc"] for e in exc.value.errors()] == [(*prefix, *parts)]


def test_s1_native_json_and_wire_dict_in_lax_python() -> None:
    original = terms(AdjustmentPolicy.PROTECTED)
    wire = original.model_dump_json()
    assert TypeAdapter(SeriesTerms).validate_json(wire, strict=False) == original
    payload = json.loads(wire)
    with pytest.raises(ValidationError) as exc:
        SeriesTerms.model_validate(payload, strict=False)
    assert {e["loc"] for e in exc.value.errors()} == {
        ("effective_on",), ("strike",), ("exercise_style",), ("adjustment_policy",),
        ("evidence", "effective_on"), ("evidence", "published_on"), ("evidence", "policy"),
    }
    payload["contract_size"] = "37"
    with pytest.raises(ValidationError) as adapter:
        TypeAdapter(SeriesTerms).validate_json(json.dumps(payload), strict=False)
    assert [e["loc"] for e in adapter.value.errors()] == [("contract_size",)]
    with pytest.raises(ValidationError) as outer:
        _Envelope.model_validate_json(json.dumps({"terms": payload}), strict=False)
    assert [e["loc"] for e in outer.value.errors()] == [("terms", "contract_size")]


@pytest.mark.parametrize("wire", [False, True])
def test_s1_unknown_style_precedes_missing_currency(wire: bool) -> None:
    data = terms().model_dump(mode="json" if wire else "python")
    del data["currency"]
    data["exercise_style"] = "UNKNOWN" if wire else ExerciseStyle.UNKNOWN
    with pytest.raises(TermsRefusal) as exc:
        if wire:
            SeriesTerms.model_validate_json(json.dumps(data), strict=False)
        else:
            SeriesTerms.model_validate(data, strict=False)
    assert exc.value.code is RefusalCode.UNKNOWN_EXERCISE_STYLE


def test_s1_unknown_evidence_preserves_inconclusive_policy() -> None:
    policy = AdjustmentPolicy.UNKNOWN
    original = SeriesTerms.model_validate(sample() | {"evidence": evidence(policy)})
    assert original.evidence is not None and original.evidence.policy is policy
    assert SeriesTerms.model_validate_json(original.model_dump_json()) == original
    with pytest.raises(ValidationError):
        original.model_copy(update={"adjustment_policy": AdjustmentPolicy.PROTECTED})


def test_s1_revalidate_instance_in_lax_container() -> None:
    invalid = SeriesTerms.model_construct(**(sample() | {"contract_size": True}))
    with pytest.raises(ValidationError) as exc:
        _Envelope.model_validate({"terms": invalid}, strict=False)
    assert [e["loc"] for e in exc.value.errors()] == [("terms", "contract_size")]


@pytest.mark.parametrize("strike", [" 176 ", "1_76", "１７６", "+176", "0176", "176.", "1.76e2"])
def test_s3_json_strike_grammar(strike: str) -> None:
    payload = terms().model_dump(mode="json") | {"strike": strike}
    for strict in (None, False):
        with pytest.raises(ValidationError) as exc:
            SeriesTerms.model_validate_json(json.dumps(payload), strict=strict)
        assert [e["loc"] for e in exc.value.errors()] == [("strike",)]


@pytest.mark.parametrize("fixed", ["176", "176.00", "0.0000001200", "0.010"])
def test_s3_fixed_json_round_trip(fixed: str) -> None:
    original = terms().model_copy(update={"strike": Decimal(fixed)})
    wire = original.model_dump_json()
    assert json.loads(wire)["strike"] == original.model_dump(mode="json")["strike"] == fixed
    restored = SeriesTerms.model_validate_json(wire, strict=False)
    assert restored.strike.as_tuple() == Decimal(fixed).as_tuple()


def test_s3_positive_exponent_has_no_lossless_fixed_representation() -> None:
    with pytest.raises(ValidationError) as exc:
        SeriesTerms.model_validate(sample() | {"strike": Decimal("1.20E+4")})
    assert [e["loc"] for e in exc.value.errors()] == [("strike",)]
