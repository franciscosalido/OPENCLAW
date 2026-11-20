"""Registro versionado de evidências fornecidas para uma série."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import StringConstraints

from backend.derivatives.domain.carry import CarryAssumption, ResolvedCarry
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
        raise RegistryRefusal(RegistryRefusalCode.MISSING)
