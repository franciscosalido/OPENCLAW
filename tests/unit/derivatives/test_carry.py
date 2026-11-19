"""Contrato da premissa de carry e sua aplicação a uma série sintética."""

import ast
import inspect
import json
import math
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from importlib.util import resolve_name
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.derivatives.domain.carry import (
    CarryAssumption,
    CarryKind,
    CarryRefusal,
    CarryRefusalCode,
    ResolvedCarry,
    resolve_carry,
)
from backend.derivatives.domain.models import ExerciseStyle
from backend.derivatives.domain.series_terms import AdjustmentPolicy, SeriesTerms, TermsRefusal
from backend.derivatives.pricing.calendar import CalendarId, load_calendars
from backend.derivatives.pricing.conventions import model_assumptions
from config.derivatives_config_model import Conventions

SYMBOL = "SYNX63"
DAY = date(2026, 1, 5)


def _terms(policy: AdjustmentPolicy) -> SeriesTerms:
    evidence = None if policy is AdjustmentPolicy.UNKNOWN else dict(
        issuer="B3", document="documento sintético", version="1", published_on=DAY,
        symbol=SYMBOL, effective_on=DAY, policy=policy,
    )
    return SeriesTerms.model_validate(dict(
        symbol=SYMBOL, effective_on=DAY, source="fixture", strike=Decimal("180"),
        contract_size=37, quotation_form=1, currency="BRL", exercise_style=ExerciseStyle.EUROPEAN,
        adjustment_policy=policy, evidence=evidence,
    ))


def _carry(kind: CarryKind, value: Decimal | None = None) -> CarryAssumption:
    return CarryAssumption(symbol=SYMBOL, effective_on=DAY, source="fonte sintética",
                           kind=kind, dividend_yield=value)


def test_protected_refuses_continuous_yield() -> None:
    """O ajuste do strike impede contar o provento no rendimento."""
    terms = _terms(AdjustmentPolicy.PROTECTED)
    assumption = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03"))
    with pytest.raises(CarryRefusal) as error:
        resolve_carry(terms, assumption)
    assert error.value.code is CarryRefusalCode.DIVIDEND_DOUBLE_COUNT


@pytest.mark.parametrize("policy", list(AdjustmentPolicy))
@pytest.mark.parametrize("yield_text", [None, "0.0001", "0.03", "0.5", "0.9999"])
def test_policy_grid(policy: AdjustmentPolicy, yield_text: str | None) -> None:
    """Toda célula aceita usa exatamente o q declarado, inclusive zero só em NONE."""
    terms = _terms(policy)
    value = None if yield_text is None else Decimal(yield_text)
    kind = CarryKind.NONE if value is None else CarryKind.CONTINUOUS_YIELD
    assumption = _carry(kind, value)
    if value is not None and policy is not AdjustmentPolicy.UNPROTECTED:
        with pytest.raises(CarryRefusal) as error:
            resolve_carry(terms, assumption)
        code = ("dividend_double_count" if policy is AdjustmentPolicy.PROTECTED
                else "strike_adjustment_unknown")
        assert str(error.value) == error.value.code.value == code
        return
    result = resolve_carry(terms, assumption)
    assert isinstance(result, ResolvedCarry)
    assert type(result.dividend_yield) is float
    assert result.dividend_yield == (0.0 if value is None else float(value))
    assert (result.dividend_yield == 0.0) == (kind is CarryKind.NONE)


@pytest.mark.parametrize("policy", list(AdjustmentPolicy))
def test_absent_assumption(policy: AdjustmentPolicy) -> None:
    """A falta de premissa precede a política da série."""
    with pytest.raises(CarryRefusal) as error:
        resolve_carry(_terms(policy), None)
    assert str(error.value) == error.value.code.value == "missing_carry_assumption"


@pytest.mark.parametrize("wire", [False, True], ids=["python", "json"])
@pytest.mark.parametrize(("kind", "code"), [
    (None, "missing_carry_assumption"), (CarryKind.DISCRETE_DIVIDENDS,
     "discrete_dividends_not_supported"), (CarryKind.CONTINUOUS_YIELD, "missing_carry_assumption"),
])
@pytest.mark.parametrize("null", [False, True], ids=["omitted", "null"])
def test_typed_refusal_first(wire: bool, kind: CarryKind | None, code: str, null: bool) -> None:
    """A primeira recusa tipada precede o erro estrutural de symbol."""
    data: dict[str, object] = {"symbol": 3}
    if kind is not None or null:
        data["kind"] = kind
    if null:
        data["dividend_yield"] = None
    with pytest.raises(CarryRefusal) as error:
        if wire:
            CarryAssumption.model_validate_json(json.dumps(data))
        else:
            CarryAssumption.model_validate(data)
    assert str(error.value) == error.value.code.value == code


@pytest.mark.parametrize("updates", [{"symbol": "OTHER"}, {"effective_on": date(2026, 1, 6)}])
def test_mismatch_precedes_policy(updates: dict[str, object]) -> None:
    """Uma declaração para outra série ou data falta mesmo com política conclusiva."""
    assumption = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03")).model_copy(update=updates)
    with pytest.raises(CarryRefusal) as error:
        resolve_carry(_terms(AdjustmentPolicy.PROTECTED), assumption)
    assert error.value.code.value == "missing_carry_assumption"


@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize(("field", "value"), [
    ("kind", "NONE"), ("kind", "CONTINUOUS_YIELD"), ("kind", "DISCRETE_DIVIDENDS"),
    ("dividend_yield", 0.03), ("dividend_yield", 1), ("dividend_yield", True),
    ("dividend_yield", "0.03"), ("dividend_yield", Decimal("0")),
    ("dividend_yield", Decimal("-0.1")), ("dividend_yield", Decimal("1")),
    ("dividend_yield", Decimal("3")), ("dividend_yield", Decimal("NaN")),
    ("dividend_yield", Decimal("sNaN")), ("dividend_yield", Decimal("Infinity")),
    ("dividend_yield", Decimal("-Infinity")), ("dividend_yield", Decimal("1e-1000")),
    ("dividend_yield", Decimal("0.99999999999999999")), ("source", "  "),
    ("effective_on", datetime(2026, 1, 5)), ("symbol", ""), ("discrete_dividends", []),
    ("effective_on", "2026-01-05"), ("symbol", b"SYN"), ("source", b"fixture"),
])
def test_python_field_errors(field: str, value: object, strict: bool) -> None:
    """A localização do erro conserva o contrato mesmo no modo permissivo."""
    fields = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03")).model_dump()
    with pytest.raises(ValidationError) as error:
        CarryAssumption.model_validate(fields | {field: value}, strict=strict)
    assert [item["loc"] for item in error.value.errors()] == [(field,)]


@pytest.mark.parametrize("field", ["symbol", "source", "effective_on"])
def test_missing_metadata(field: str) -> None:
    """Fonte e data são obrigatórias."""
    data = _carry(CarryKind.NONE).model_dump()
    del data[field]
    with pytest.raises(ValidationError) as error:
        CarryAssumption.model_validate(data)
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("0.03")])
def test_none_has_no_yield(value: Decimal) -> None:
    """Qualquer rendimento explícito contradiz NONE."""
    with pytest.raises(ValidationError) as error:
        _carry(CarryKind.NONE, value)
    assert error.value.errors()[0]["loc"] == ("dividend_yield",)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(("field", "value"), [
    ("kind", 3), ("kind", True), ("kind", "other"), ("dividend_yield", 0.03),
    ("dividend_yield", 1), ("dividend_yield", True), ("dividend_yield", "3e-2"),
    ("dividend_yield", ".03"), ("dividend_yield", "+0.03"), ("dividend_yield", "00.03"),
    ("dividend_yield", "0.٠٣"), ("dividend_yield", "0." + "0" * 999 + "1"),
    ("dividend_yield", "0.99999999999999999"), ("effective_on", "20260105"),
])
def test_json_field_errors(field: str, value: object, strict: bool) -> None:
    """A entrada JSON exige enum textual, data ISO e rendimento decimal fixo ASCII."""
    data = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03")).model_dump(mode="json")
    with pytest.raises(ValidationError) as error:
        CarryAssumption.model_validate_json(json.dumps(data | {field: value}), strict=strict)
    assert [item["loc"] for item in error.value.errors()] == [(field,)]


@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("value", ["0.0300", "0.000000001200", None])
def test_json_preserves_types_and_scale(value: str | None, strict: bool) -> None:
    """O formato fixo conserva a tupla decimal e os tipos Python após persistência."""
    original = (_carry(CarryKind.NONE) if value is None else
                _carry(CarryKind.CONTINUOUS_YIELD, Decimal(value)))
    payload = original.model_dump_json()
    assert json.loads(payload)["dividend_yield"] == value
    for restored in (CarryAssumption.model_validate_json(payload, strict=strict),
                     CarryAssumption.model_validate(original.model_dump(), strict=strict)):
        assert restored == original
        assert type(restored.kind) is CarryKind and type(restored.effective_on) is date
        if value is not None:
            assert type(restored.dividend_yield) is Decimal
            assert restored.dividend_yield.as_tuple() == Decimal(value).as_tuple()


@pytest.mark.parametrize("q", [math.nextafter(0.0, 1.0), math.nextafter(1.0, 0.0)])
def test_representable_endpoints(q: float) -> None:
    """Os vizinhos float internos de 0 e 1 continuam utilizáveis."""
    carry = _carry(CarryKind.CONTINUOUS_YIELD, Decimal.from_float(q))
    assert resolve_carry(_terms(AdjustmentPolicy.UNPROTECTED), carry).dividend_yield == q


def test_frozen_models_and_revalidated_copy() -> None:
    """A premissa e o resultado são imutáveis e a cópia atualizada passa pelas recusas."""
    carry = _carry(CarryKind.NONE)
    with pytest.raises(ValidationError):
        setattr(carry, "kind", CarryKind.CONTINUOUS_YIELD)
    with pytest.raises(CarryRefusal) as error:
        carry.model_copy(update={"kind": CarryKind.CONTINUOUS_YIELD})
    assert error.value.code.value == "missing_carry_assumption"
    result = resolve_carry(_terms(AdjustmentPolicy.UNKNOWN), carry)
    with pytest.raises((FrozenInstanceError, ValidationError)):
        setattr(result, "dividend_yield", 0.3)


@pytest.mark.parametrize(("updates", "code"), [
    ({"exercise_style": ExerciseStyle.UNKNOWN}, "unknown_exercise_style"),
    ({"contract_size": None}, "missing_contract_size"),
    ({"adjustment_policy": AdjustmentPolicy.PROTECTED}, None),
])
def test_revalidate_constructed_terms(updates: dict[str, object], code: str | None) -> None:
    """Termos construídos sem validação passam pela precedência do PR01."""
    fields = _terms(AdjustmentPolicy.UNKNOWN).model_dump() | updates
    forged = SeriesTerms.model_construct(**fields)
    if code is None:
        with pytest.raises(ValidationError):
            resolve_carry(forged, None)
    else:
        with pytest.raises(TermsRefusal) as error:
            resolve_carry(forged, None)
        assert error.value.code.value == code


@pytest.mark.parametrize(("updates", "code"), [
    ({"kind": CarryKind.CONTINUOUS_YIELD}, "missing_carry_assumption"),
    ({"kind": CarryKind.DISCRETE_DIVIDENDS}, "discrete_dividends_not_supported"),
    ({"kind": CarryKind.CONTINUOUS_YIELD, "dividend_yield": Decimal(5)}, None),
])
def test_revalidate_constructed_carry(updates: dict[str, object], code: str | None) -> None:
    """A revalidação precede a comparação da série e a matriz."""
    fields = _carry(CarryKind.NONE).model_dump() | updates | {"symbol": "OTHER"}
    forged = CarryAssumption.model_construct(**fields)
    if code is None:
        with pytest.raises(ValidationError) as invalid:
            resolve_carry(_terms(AdjustmentPolicy.UNKNOWN), forged)
        assert invalid.value.errors()[0]["loc"] == ("dividend_yield",)
    else:
        with pytest.raises(CarryRefusal) as error:
            resolve_carry(_terms(AdjustmentPolicy.UNKNOWN), forged)
        assert error.value.code.value == code


class _OtherTerms(SeriesTerms):
    """Tipo derivado que declara os mesmos campos."""


class _OtherAssumption(CarryAssumption):
    """Tipo derivado que declara os mesmos campos."""


def test_revalidates_subclasses_and_tampered_instances() -> None:
    """Reconstrói os dois registros base e examina os campos até em instâncias prontas."""
    terms = _OtherTerms.model_validate(_terms(AdjustmentPolicy.UNPROTECTED).model_dump())
    carry = _OtherAssumption.model_validate(_carry(CarryKind.NONE).model_dump())
    result = resolve_carry(terms, carry)
    assert type(result.terms) is SeriesTerms and result.terms is not terms
    assert type(result.assumption) is CarryAssumption and result.assumption is not carry
    carry.__dict__["kind"] = CarryKind.DISCRETE_DIVIDENDS
    with pytest.raises(CarryRefusal) as invalid:
        resolve_carry(terms, carry)
    assert invalid.value.code.value == "discrete_dividends_not_supported"
    terms.__dict__["contract_size"] = None
    with pytest.raises(TermsRefusal) as refusal:
        resolve_carry(terms, carry)
    assert refusal.value.code.value == "missing_contract_size"


def test_required_arguments_and_no_config_import() -> None:
    """A função exige os dois argumentos e conserva sua independência de configuração."""
    parameters = inspect.signature(resolve_carry).parameters
    assert tuple(parameters) == ("terms", "carry")
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters.values())
    with pytest.raises(TypeError):
        resolve_carry(_terms(AdjustmentPolicy.UNKNOWN))  # type: ignore[call-arg]
    tree = ast.parse(Path(inspect.getfile(resolve_carry)).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            module = resolve_name("." * node.level + (node.module or ""),
                                  "backend.derivatives.domain")
            imports.update([module, *(f"{module}.{alias.name}" for alias in node.names)])
    for prefix in ("config", "backend.derivatives.config", "backend.derivatives.pricing"):
        assert all(name != prefix and not name.startswith(prefix + ".") for name in imports)


@pytest.mark.parametrize("value", [None, Decimal("0.0300")])
def test_assumptions(value: Decimal | None) -> None:
    """O resultado expõe cinco hipóteses disjuntas das convenções da Fase 01."""
    kind = CarryKind.NONE if value is None else CarryKind.CONTINUOUS_YIELD
    terms = _terms(AdjustmentPolicy.UNPROTECTED)
    carry = _carry(kind, value)
    result = resolve_carry(terms, carry)
    assert result.terms == terms and result.terms is not terms
    assert result.assumption == carry and result.assumption is not carry
    assumptions = result.assumptions()
    assert assumptions == {
        "carry_kind": kind.value, "carry_dividend_yield": 0.0 if value is None else float(value),
        "carry_source": "fonte sintética", "carry_effective_on": "2026-01-05",
        "strike_adjustment_policy": "UNPROTECTED",
    }
    assert all(type(v) is (float if k == "carry_dividend_yield" else str)
               for k, v in assumptions.items())
    cfg = Conventions()
    cal = load_calendars(cfg, root=Path("."))[CalendarId.B3_LISTED_TRADING]
    assert assumptions.keys().isdisjoint(model_assumptions(cfg, cal))


def test_omitted_yield_for_none() -> None:
    """Ausência e nulo são aceitos para uma premissa NONE explicitamente declarada."""
    fields = _carry(CarryKind.NONE).model_dump(exclude_none=True)
    carry = CarryAssumption.model_validate(fields)
    assert carry.kind is CarryKind.NONE and carry.dividend_yield is None
    assert resolve_carry(_terms(AdjustmentPolicy.PROTECTED), carry).dividend_yield == 0.0


def test_mutated_base_instances_are_revalidated() -> None:
    """Alterações no dicionário interno de uma instância exata atravessam a validação."""
    terms = _terms(AdjustmentPolicy.UNKNOWN)
    carry = _carry(CarryKind.NONE)
    carry.__dict__["dividend_yield"] = Decimal("0.25")
    with pytest.raises(ValidationError) as invalid:
        resolve_carry(terms, carry)
    assert invalid.value.errors()[0]["loc"] == ("dividend_yield",)
    terms.__dict__["adjustment_policy"] = AdjustmentPolicy.PROTECTED
    with pytest.raises(ValidationError) as invalid_terms:
        resolve_carry(terms, carry)
    assert invalid_terms.value.errors()[0]["loc"] == ()


@pytest.mark.parametrize("policy", list(AdjustmentPolicy))
@pytest.mark.parametrize("updates", [{"symbol": "OTHER"}, {"effective_on": date(2026, 1, 6)}])
def test_none_for_another_series_or_date_is_missing(
    policy: AdjustmentPolicy, updates: dict[str, object],
) -> None:
    """NONE declarado para outra série ou outra data não vira q = 0 nesta (revisão, R01)."""
    assumption = _carry(CarryKind.NONE).model_copy(update=updates)
    with pytest.raises(CarryRefusal) as error:
        resolve_carry(_terms(policy), assumption)
    assert str(error.value) == error.value.code.value == "missing_carry_assumption"


class _LooseDecimal(Decimal):
    """Subclasse que responde outro valor na conversão para float."""

    def __float__(self) -> float:
        return 0.5


@pytest.mark.parametrize("strict", [True, False])
def test_decimal_subclass_is_rejected(strict: bool) -> None:
    """O rendimento exige Decimal exato: a subclasse poderia mentir em float() (revisão, R07b)."""
    fields = _carry(CarryKind.CONTINUOUS_YIELD, Decimal("0.03")).model_dump()
    with pytest.raises(ValidationError) as error:
        CarryAssumption.model_validate(fields | {"dividend_yield": _LooseDecimal("7")},
                                       strict=strict)
    assert [item["loc"] for item in error.value.errors()] == [("dividend_yield",)]
