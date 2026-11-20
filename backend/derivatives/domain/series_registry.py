"""Registro versionado de evidências fornecidas para uma série."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import StringConstraints, model_validator

from backend.derivatives.domain.carry import CarryAssumption, ResolvedCarry, resolve_carry
from backend.derivatives.domain.models import OptionContract, OptionKind
from backend.derivatives.domain.series_terms import SeriesTerms, _CivilDate, _input_type, _TermsModel

_Identifier = Annotated[str, StringConstraints(pattern=r"\S"), _input_type(str)]


class RegistryRefusalCode(StrEnum):
    MISSING = "missing_series_record"
    EXPIRED = "expired_series_record"
    FUTURE = "future_series_record"
    CONFLICT = "conflicting_series_records"
    MISMATCH = "series_contract_mismatch"


class RegistryRefusal(Exception):
    def __init__(self, code: RegistryRefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class SeriesRecord(_TermsModel):
    version: _Identifier
    underlying: _Identifier
    kind: Annotated[OptionKind, _input_type(OptionKind, json=str)]
    expiry: _CivilDate
    isin: _Identifier | None
    terms: SeriesTerms
    carry: CarryAssumption | None
    available_on: _CivilDate
    valid_through: _CivilDate

    @model_validator(mode="after")
    def _ordered_interval(self) -> Self:
        if self.valid_through < self.terms.effective_on:
            raise ValueError("intervalo de vigência invertido")
        return self


@dataclass(frozen=True, slots=True)
class SeriesResolution:
    as_of: date
    registry_version: str
    record: SeriesRecord
    carry: ResolvedCarry


class SeriesRegistry(_TermsModel):
    version: _Identifier
    records: tuple[SeriesRecord, ...]

    def resolve(self, contract: OptionContract, *, as_of: date) -> SeriesResolution:
        if type(as_of) is not date:
            raise ValueError("as_of deve ser data civil")
        # OptionContract permite model_copy(update=...) sem validação.
        contract = OptionContract.model_validate(
            {name: getattr(contract, name) for name in OptionContract.model_fields}, strict=True,
        )
        book = SeriesRegistry.model_validate(self)
        same_symbol = [row for row in book.records if row.terms.symbol == contract.symbol]
        if not same_symbol:
            raise RegistryRefusal(RegistryRefusalCode.MISSING)
        matches = [
            row for row in same_symbol
            if (row.underlying, row.kind, row.expiry, row.terms.strike, row.isin)
            == (contract.underlying, contract.kind, contract.expiry, contract.strike, contract.isin)
        ]
        if not matches:
            raise RegistryRefusal(RegistryRefusalCode.MISMATCH)
        known = [row for row in matches if row.available_on <= as_of]
        if len({row.version for row in known}) != len(known):
            raise RegistryRefusal(RegistryRefusalCode.CONFLICT)
        started = [row for row in known if row.terms.effective_on <= as_of]
        if not started:
            raise RegistryRefusal(RegistryRefusalCode.FUTURE)
        valid = [row for row in started if as_of <= row.valid_through]
        if not valid:
            raise RegistryRefusal(RegistryRefusalCode.EXPIRED)
        if len(valid) != 1:
            raise RegistryRefusal(RegistryRefusalCode.CONFLICT)
        row = valid[0]
        terms = row.terms
        if (
            contract.exercise_style != terms.exercise_style
            or (contract.contract_size is not None and contract.contract_size != terms.contract_size)
            or (contract.quotation_form is not None and contract.quotation_form != terms.quotation_form)
        ):
            raise RegistryRefusal(RegistryRefusalCode.MISMATCH)
        return SeriesResolution(as_of, book.version, row, resolve_carry(terms, row.carry))
