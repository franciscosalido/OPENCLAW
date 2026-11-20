"""Registro versionado de evidências fornecidas para uma série."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import StringConstraints, model_validator

from backend.derivatives.domain.carry import CarryAssumption, ResolvedCarry, resolve_carry
from backend.derivatives.domain.models import OptionContract, OptionKind
from backend.derivatives.domain.series_terms import (
    SeriesTerms, _CivilDate, _input_type, _TermsModel,
)

_Identifier = Annotated[str, StringConstraints(pattern=r"\S"), _input_type(str)]


class RegistryRefusalCode(StrEnum):
    """Motivos estáveis de recusa da consulta ao registro."""

    MISSING = "missing_series_record"
    EXPIRED = "expired_series_record"
    FUTURE = "future_series_record"
    CONFLICT = "conflicting_series_records"
    MISMATCH = "series_contract_mismatch"


class RegistryRefusal(Exception):
    """Recusa tipada: nenhum registro único e vigente serve ao contrato."""

    def __init__(self, code: RegistryRefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class SeriesRecord(_TermsModel):
    """Versão fornecida de termos e carry, com último dia de validade declarado."""

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
    """Evidência selecionada e premissa validada à data da consulta."""

    as_of: date
    registry_version: str
    record: SeriesRecord
    carry: ResolvedCarry


def _applicable_record(records: list[SeriesRecord], as_of: date) -> SeriesRecord:
    """Seleciona dentro de uma única identidade, respeitando a disponibilidade histórica."""
    known = [row for row in records if row.available_on <= as_of]
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
    return valid[0]


class SeriesRegistry(_TermsModel):
    """Conjunto versionado fornecido pelo chamador, sem seleção de fonte ou prazo padrão."""

    version: _Identifier
    records: tuple[SeriesRecord, ...]

    def resolve(self, contract: OptionContract, *, as_of: date) -> SeriesResolution:
        """Confere identidade, vigência e metadados antes de resolver o rendimento."""
        if type(as_of) is not date:
            raise ValueError("as_of deve ser data civil")
        if not isinstance(contract, OptionContract):
            raise TypeError("a consulta exige OptionContract")
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
        row = _applicable_record(matches, as_of)
        terms = row.terms
        size, form = contract.contract_size, contract.quotation_form
        if (
            contract.exercise_style != terms.exercise_style
            or (size is not None and size != terms.contract_size)
            or (form is not None and form != terms.quotation_form)
        ):
            raise RegistryRefusal(RegistryRefusalCode.MISMATCH)
        return SeriesResolution(as_of, book.version, row, resolve_carry(terms, row.carry))
