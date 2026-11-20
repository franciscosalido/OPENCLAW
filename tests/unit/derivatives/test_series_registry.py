"""Registros e documentos inteiramente SINTÉTICOS; somente para testes de domínio."""

from datetime import date, datetime
from decimal import Decimal
from itertools import permutations
from typing import cast

import pytest
from pydantic import ValidationError

from backend.derivatives.domain.carry import CarryAssumption, CarryKind, CarryRefusal
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_registry import RegistryRefusal, SeriesRecord, SeriesRegistry
from backend.derivatives.domain.series_terms import AdjustmentEvidence, AdjustmentPolicy, SeriesTerms


def day(n: int) -> date:
    return date(2026, 4, n)


@pytest.fixture
def contract() -> OptionContract:
    return OptionContract(
        symbol="SYNTHETIC-C", underlying="SYNTHETIC-U", kind=OptionKind.CALL,
        exercise_style=ExerciseStyle.AMERICAN, strike=Decimal("12.50"), expiry=day(30),
        contract_size=7, quotation_form=1, isin="SYNTHETIC-ISIN",
    )


@pytest.fixture
def record(contract: OptionContract) -> SeriesRecord:
    terms = SeriesTerms(
        symbol=contract.symbol, strike=Decimal("12.50"), exercise_style=ExerciseStyle.AMERICAN,
        contract_size=7, quotation_form=1, currency="BRL", adjustment_policy=AdjustmentPolicy.UNKNOWN,
        effective_on=day(4), source="SYNTHETIC terms",
    )
    carry = CarryAssumption(
        symbol=contract.symbol, kind=CarryKind.NONE, source="SYNTHETIC carry", effective_on=day(4),
    )
    return SeriesRecord(
        version="z-first", terms=terms, carry=carry, underlying="SYNTHETIC-U", kind=OptionKind.CALL,
        expiry=day(30), isin="SYNTHETIC-ISIN", available_on=day(3), valid_through=day(8),
    )


def registry(*records: SeriesRecord) -> SeriesRegistry:
    return SeriesRegistry(version="SYNTHETIC snapshot/v3", records=records)


@pytest.fixture
def later(record: SeriesRecord) -> SeriesRecord:
    assert record.carry is not None
    return record.model_copy(update={
        "version": "a-second", "available_on": day(11), "valid_through": day(15),
        "terms": record.terms.model_copy(update={"effective_on": day(10), "source": "SYNTHETIC v2"}),
        "carry": record.carry.model_copy(update={"effective_on": day(10)}),
    })


@pytest.mark.parametrize(("n", "expected"), [
    (2, "future_series_record"), (3, "future_series_record"), (4, "z-first"),
    (8, "z-first"), (9, "expired_series_record"), (10, "expired_series_record"),
    (11, "a-second"), (15, "a-second"), (16, "expired_series_record"),
])
def test_historical_selection(contract: OptionContract, record: SeriesRecord,
                              later: SeriesRecord, n: int, expected: str) -> None:
    for order in permutations((record, later)):
        book = registry(*order)
        if expected.endswith("_series_record"):
            with pytest.raises(RegistryRefusal) as exc:
                book.resolve(contract, as_of=day(n))
            assert exc.value.code.value == expected
        else:
            result = book.resolve(contract, as_of=day(n))
            chosen = record if expected == "z-first" else later
            assert result.record == chosen
            assert result.as_of == day(n)
            assert result.registry_version == "SYNTHETIC snapshot/v3"
            assert result.carry.terms == chosen.terms
            assert result.carry.assumption == chosen.carry
            assert result.carry.dividend_yield == 0.0


def test_retroactive_evidence_requires_availability(contract: OptionContract, later: SeriesRecord) -> None:
    with pytest.raises(RegistryRefusal) as exc:
        registry(later).resolve(contract, as_of=day(10))
    assert exc.value.code.value == "future_series_record"


@pytest.mark.parametrize("empty", [True, False])
def test_absent(contract: OptionContract, record: SeriesRecord, empty: bool) -> None:
    other = contract.model_copy(update={"symbol": "SYNTHETIC-OTHER"})
    with pytest.raises(RegistryRefusal) as exc:
        (registry() if empty else registry(record)).resolve(other, as_of=day(5))
    assert exc.value.code.value == "missing_series_record"


@pytest.mark.parametrize(("field", "value"), [
    ("strike", Decimal("12.51")), ("expiry", day(29)), ("isin", "SYNTHETIC-OTHER"),
    ("isin", None), ("kind", OptionKind.PUT), ("underlying", "SYNTHETIC-V"),
    ("exercise_style", ExerciseStyle.EUROPEAN), ("contract_size", 8), ("quotation_form", 1000),
])
def test_same_symbol_does_not_authorize_terms(contract: OptionContract, record: SeriesRecord,
                                             field: str, value: object) -> None:
    with pytest.raises(RegistryRefusal) as exc:
        registry(record).resolve(contract.model_copy(update={field: value}), as_of=day(6))
    assert exc.value.code.value == "series_contract_mismatch"


def test_homonyms_and_missing_isin(contract: OptionContract, record: SeriesRecord) -> None:
    other = record.model_copy(update={"isin": None, "carry": None})
    for order in permutations((other, record)):
        assert registry(*order).resolve(contract, as_of=day(6)).record == record
        with pytest.raises(CarryRefusal) as exc:
            registry(*order).resolve(contract.model_copy(update={"isin": None}), as_of=day(6))
        assert exc.value.code.value == "missing_carry_assumption"


@pytest.mark.parametrize(("lot", "factor", "matches"), [
    (None, None, True), (None, 1, True), (7, None, True), (None, 1000, False), (8, None, False),
])
def test_optional_contract_metadata(contract: OptionContract, record: SeriesRecord,
                                    lot: int | None, factor: int | None, matches: bool) -> None:
    observed = contract.model_copy(update={"contract_size": lot, "quotation_form": factor})
    if matches:
        assert registry(record).resolve(observed, as_of=day(5)).record.terms.contract_size == 7
        assert (observed.contract_size, observed.quotation_form) == (lot, factor)
    else:
        with pytest.raises(RegistryRefusal) as exc:
            registry(record).resolve(observed, as_of=day(5))
        assert exc.value.code.value == "series_contract_mismatch"


@pytest.mark.parametrize("revision", ["z-first", "other"])
def test_ambiguous_even_at_last_day(contract: OptionContract, record: SeriesRecord,
                                    revision: str) -> None:
    other = record if revision == record.version else record.model_copy(update={
        "version": revision, "available_on": day(8), "carry": None,
    })
    for order in permutations((record, other)):
        with pytest.raises(RegistryRefusal) as exc:
            registry(*order).resolve(contract, as_of=day(8))
        assert exc.value.code.value == "conflicting_series_records"


def test_reused_version_cannot_rewrite_history(contract: OptionContract, record: SeriesRecord,
                                               later: SeriesRecord) -> None:
    later = later.model_copy(update={"version": record.version})
    for order in permutations((record, later)):
        assert registry(*order).resolve(contract, as_of=day(4)).record == record
        with pytest.raises(RegistryRefusal) as exc:
            registry(*order).resolve(contract, as_of=day(11))
        assert exc.value.code.value == "conflicting_series_records"


@pytest.mark.parametrize("change", [None, {"symbol": "SYNTHETIC-OTHER"}, {"effective_on": day(5)}])
def test_absent_or_inapplicable_carry(contract: OptionContract, record: SeriesRecord,
                                      change: dict[str, object] | None) -> None:
    assert record.carry is not None
    candidate = record.model_copy(update={"carry": None if change is None else
                                          record.carry.model_copy(update=change)})
    with pytest.raises(CarryRefusal) as exc:
        registry(candidate).resolve(contract, as_of=day(6))
    assert exc.value.code.value == "missing_carry_assumption"


@pytest.mark.parametrize(("policy", "reason"), [
    (AdjustmentPolicy.PROTECTED, "dividend_double_count"),
    (AdjustmentPolicy.UNKNOWN, "strike_adjustment_unknown"),
    (AdjustmentPolicy.UNPROTECTED, None),
])
def test_continuous_carry_uses_declared_policy(contract: OptionContract, record: SeriesRecord,
                                               policy: AdjustmentPolicy, reason: str | None) -> None:
    document = None if policy is AdjustmentPolicy.UNKNOWN else AdjustmentEvidence(
        issuer="B3", document="SYNTHETIC test document", version="SYNTHETIC 1",
        published_on=day(1), effective_on=day(4), symbol=contract.symbol, policy=policy,
    )
    terms = record.terms.model_copy(update={"adjustment_policy": policy, "evidence": document})
    carry = CarryAssumption(
        symbol=contract.symbol, effective_on=day(4), kind=CarryKind.CONTINUOUS_YIELD,
        source="SYNTHETIC declared q", dividend_yield=Decimal("0.013"),
    )
    book = registry(record.model_copy(update={"terms": terms, "carry": carry}))
    if reason is None:
        result = book.resolve(contract, as_of=day(7))
        assert result.record.terms.evidence == document
        assert result.carry.assumption == carry
        assert result.carry.dividend_yield == 0.013
    else:
        with pytest.raises(CarryRefusal) as exc:
            book.resolve(contract, as_of=day(7))
        assert exc.value.code.value == reason


@pytest.mark.parametrize("change", [
    {"valid_through": day(3)}, {"valid_through": "2026-04-08"}, {"available_on": datetime(2026, 4, 3)},
    {"expiry": "2026-04-30"}, {"kind": "CALL"}, {"version": ""}, {"isin": 123},
])
def test_malformed_record_rejected(record: SeriesRecord, change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        record.model_copy(update=change)


@pytest.mark.parametrize("bad_day", ["2026-04-06", datetime(2026, 4, 6)])
def test_requires_civil_query_date(contract: OptionContract, record: SeriesRecord, bad_day: object) -> None:
    with pytest.raises(ValueError):
        registry(record).resolve(contract, as_of=cast(date, bad_day))


@pytest.mark.parametrize("change", [{"kind": "CALL"}, {"strike": 12.5}, {"quotation_form": True}])
def test_rejects_unvalidated_contract_copies(contract: OptionContract, record: SeriesRecord,
                                             change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        registry(record).resolve(contract.model_copy(update=change), as_of=day(6))


def test_round_trip_keeps_versions_decimal_scale_and_sources(record: SeriesRecord) -> None:
    original = registry(record)
    restored = SeriesRegistry.model_validate_json(original.model_dump_json())
    assert restored == original
    assert str(restored.records[0].terms.strike) == "12.50"
