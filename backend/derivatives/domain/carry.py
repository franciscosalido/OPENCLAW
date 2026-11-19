"""Premissa explícita de rendimento por série e vigência (DL2-PR02)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import Field, ValidationInfo, field_serializer, field_validator, model_validator

from backend.derivatives.domain.series_terms import (
    _FIXED_DECIMAL,
    AdjustmentPolicy,
    SeriesTerms,
    Text,
    _CivilDate,
    _input_mapping,
    _input_type,
    _TermsModel,
)


class CarryKind(StrEnum):
    """Forma declarada do rendimento do ativo-objeto."""

    NONE = "NONE"
    CONTINUOUS_YIELD = "CONTINUOUS_YIELD"
    DISCRETE_DIVIDENDS = "DISCRETE_DIVIDENDS"


class CarryRefusalCode(StrEnum):
    """Motivos de recusa da premissa de carry definidos no ADR-0025."""

    MISSING_CARRY_ASSUMPTION = "missing_carry_assumption"
    DIVIDEND_DOUBLE_COUNT = "dividend_double_count"
    STRIKE_ADJUSTMENT_UNKNOWN = "strike_adjustment_unknown"
    DISCRETE_DIVIDENDS_NOT_SUPPORTED = "discrete_dividends_not_supported"


class CarryRefusal(Exception):
    """Recusa de domínio que expõe somente o código estável."""

    def __init__(self, code: CarryRefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class CarryAssumption(_TermsModel):
    """Rendimento contínuo anualizado em fração, na base business_252 dos termos."""

    symbol: Text
    effective_on: _CivilDate
    source: Text
    kind: Annotated[CarryKind, _input_type(CarryKind, json=str)]
    dividend_yield: Decimal | None = Field(default=None, validate_default=True)

    @model_validator(mode="before")
    @classmethod
    def _require_kind(cls, data: object) -> dict[str, object]:
        fields = _input_mapping(data)
        if fields.get("kind") is None:
            raise CarryRefusal(CarryRefusalCode.MISSING_CARRY_ASSUMPTION)
        return fields

    @field_validator("kind")
    @classmethod
    def _supported_kind(cls, kind: CarryKind) -> CarryKind:
        if kind is CarryKind.DISCRETE_DIVIDENDS:
            raise CarryRefusal(CarryRefusalCode.DISCRETE_DIVIDENDS_NOT_SUPPORTED)
        return kind

    @field_validator("dividend_yield", mode="before")
    @classmethod
    def _continuous_yield(cls, value: object, info: ValidationInfo) -> Decimal | None:
        kind = info.data.get("kind")
        if value is None:
            if kind is CarryKind.CONTINUOUS_YIELD:
                raise CarryRefusal(CarryRefusalCode.MISSING_CARRY_ASSUMPTION)
            return None
        if kind is CarryKind.NONE:
            raise ValueError("NONE exige rendimento ausente ou nulo")
        if info.mode == "json":
            if not isinstance(value, str) or not _FIXED_DECIMAL.fullmatch(value):
                raise ValueError("rendimento JSON deve ser texto decimal fixo ASCII")
            value = Decimal(value)
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("rendimento deve ser Decimal finito")
        # O intervalo aberto deve sobreviver ao arredondamento usado pelo motor.
        if not 0 < float(value) < 1:
            raise ValueError("rendimento deve permanecer entre zero e um em float")
        return value

    @field_serializer("dividend_yield", when_used="json-unless-none")
    def _fixed_yield(self, value: Decimal) -> str:
        return format(value, "f")


@dataclass(frozen=True, slots=True)
class ResolvedCarry:
    """Termos, premissa aplicável e rendimento entregue ao modelo."""

    terms: SeriesTerms
    assumption: CarryAssumption
    dividend_yield: float

    def assumptions(self) -> dict[str, str | float]:
        """Expõe a premissa utilizada e a política de ajuste declarada nos termos."""
        return {
            "carry_kind": self.assumption.kind.value,
            "carry_dividend_yield": self.dividend_yield,
            "carry_source": self.assumption.source,
            "carry_effective_on": self.assumption.effective_on.isoformat(),
            "strike_adjustment_policy": self.terms.adjustment_policy.value,
        }


def resolve_carry(terms: SeriesTerms, carry: CarryAssumption | None) -> ResolvedCarry:
    """Revalida os registros e aplica a trava de dupla contagem à série e à data."""
    terms = SeriesTerms.model_validate(terms)
    if carry is None:
        raise CarryRefusal(CarryRefusalCode.MISSING_CARRY_ASSUMPTION)
    assumption = CarryAssumption.model_validate(carry)
    if assumption.symbol != terms.symbol or assumption.effective_on != terms.effective_on:
        raise CarryRefusal(CarryRefusalCode.MISSING_CARRY_ASSUMPTION)
    if assumption.kind is CarryKind.NONE:
        return ResolvedCarry(terms, assumption, 0.0)
    if terms.adjustment_policy is AdjustmentPolicy.PROTECTED:
        raise CarryRefusal(CarryRefusalCode.DIVIDEND_DOUBLE_COUNT)
    if terms.adjustment_policy is AdjustmentPolicy.UNKNOWN:
        raise CarryRefusal(CarryRefusalCode.STRIKE_ADJUSTMENT_UNKNOWN)
    assert assumption.dividend_yield is not None  # CONTINUOUS_YIELD revalidado acima
    return ResolvedCarry(terms, assumption, float(assumption.dividend_yield))
