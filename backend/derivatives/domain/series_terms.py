"""Termos vigentes por série (DL2-PR01), independentes da chain da Fase 01."""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from warnings import warn

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from backend.derivatives.domain.models import ExerciseStyle


class RefusalCode(StrEnum):
    """Motivo do ADR-0025 para um termo ausente ou estilo explicitamente desconhecido."""

    MISSING_CONTRACT_SIZE = "missing_contract_size"
    MISSING_QUOTATION_FORM = "missing_quotation_form"
    UNKNOWN_EXERCISE_STYLE = "unknown_exercise_style"
    UNKNOWN_CURRENCY = "unknown_currency"


class TermsRefusal(Exception):
    """Primeira recusa de domínio da observação, identificada pelo código estável do ADR."""

    def __init__(self, code: RefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class AdjustmentPolicy(StrEnum):
    """PROTECTED indica ajuste do strike pela bolsa por proventos, conforme documento aplicável.

    INDOPC identifica correção por indexador (inclusive IGP-M). O rótulo Refer. Protected
    também exige definição documental antes de qualquer interpretação por série e vigência.
    """

    PROTECTED = "PROTECTED"
    UNPROTECTED = "UNPROTECTED"
    UNKNOWN = "UNKNOWN"


def _input_type(python: type[object], *, json: type[object] | None = None) -> BeforeValidator:
    """Exige o tipo do campo antes que o parser possa aplicar coerções do chamador."""
    def check(value: object, info: ValidationInfo) -> object:
        expected = json if info.mode == "json" and json is not None else python
        if type(value) is not expected:
            raise ValueError(f"tipo esperado: {expected.__name__}")
        return value

    return BeforeValidator(check)


_string_input = _input_type(str)
_integer_input = _input_type(int)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), _string_input]
_Policy = Annotated[AdjustmentPolicy, _input_type(AdjustmentPolicy, json=str)]
_Style = Annotated[ExerciseStyle, _input_type(ExerciseStyle, json=str)]
_FIXED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
TERMS_CONFIG = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always")


def _input_mapping(data: object) -> dict[str, object]:
    if not isinstance(data, Mapping):
        raise ValueError("termos e evidências exigem um mapping ou objeto JSON")
    return dict(data)


def _civil_date(value: object, info: ValidationInfo) -> date:
    if info.mode == "json":
        if not isinstance(value, str):
            raise ValueError("data JSON deve ser texto")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("data JSON deve estar no formato AAAA-MM-DD")
        return parsed
    if type(value) is not date:
        raise ValueError("data civil deve ser date")
    return value


_CivilDate = Annotated[date, BeforeValidator(_civil_date)]


class _TermsModel(BaseModel):
    model_config = TERMS_CONFIG

    def model_copy(self, *, update: Mapping[str, object] | None = None, deep: bool = False) -> Self:
        """Copia conforme deep. Uma atualização reconstrói e valida o registro completo."""
        if not update:
            return super().model_copy(deep=deep)
        fields = self.model_dump(exclude_unset=True)
        return type(self).model_validate({**fields, **update})

    def copy(
        self, *, include: object = None, exclude: object = None,
        update: dict[str, object] | None = None, deep: bool = False,
    ) -> Self:
        """Encaminha a API legada à cópia validada de registros completos."""
        warn("copy está obsoleto, use model_copy", DeprecationWarning, stacklevel=2)
        if include is not None or exclude is not None:
            raise ValueError("para projetar campos use model_dump(include=..., exclude=...)")
        return self.model_copy(update=update, deep=deep)


class AdjustmentEvidence(_TermsModel):
    """Declaração documental fornecida pelo chamador; não consulta o emissor."""

    issuer: Annotated[Literal["B3"], _string_input]
    document: Text
    version: Text
    published_on: _CivilDate
    symbol: Text
    effective_on: _CivilDate
    policy: _Policy
    _require_mapping = model_validator(mode="before")(_input_mapping)

    @model_validator(mode="after")
    def _published_by_effective_date(self) -> Self:
        if self.published_on > self.effective_on:
            raise ValueError("documento publicado depois da vigência observada")
        return self


class SeriesTerms(_TermsModel):
    """Uma observação por série e data de vigência explícita.

    FATCOT admite neste recorte cotação por unidade (1) ou por mil (1000),
    conforme o layout COTAHIST rev. 02, p. 6. O lote tem fonte própria.
    """

    symbol: Text
    effective_on: _CivilDate
    source: Text
    strike: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    contract_size: Annotated[int, Field(gt=0), _integer_input]
    quotation_form: Annotated[Literal[1, 1000], _integer_input]
    exercise_style: _Style
    currency: Annotated[Literal["BRL"], _string_input]
    adjustment_policy: _Policy
    evidence: AdjustmentEvidence | None = None

    @model_validator(mode="before")
    @classmethod
    def require_series_fields(cls, data: object) -> object:
        """Mantém a precedência das recusas de lote, fator, estilo e moeda."""
        fields = _input_mapping(data)
        if fields.get("contract_size") is None:
            raise TermsRefusal(RefusalCode.MISSING_CONTRACT_SIZE)
        if fields.get("quotation_form") is None:
            raise TermsRefusal(RefusalCode.MISSING_QUOTATION_FORM)
        if fields.get("exercise_style") is None:
            raise TermsRefusal(RefusalCode.UNKNOWN_EXERCISE_STYLE)
        # A ausência de moeda é avaliada depois do sentinela de estilo já interpretado.
        fields.setdefault("currency", None)
        return fields

    @field_validator("exercise_style", mode="after")
    @classmethod
    def _known_style(cls, value: ExerciseStyle) -> ExerciseStyle:
        if value is ExerciseStyle.UNKNOWN:
            raise TermsRefusal(RefusalCode.UNKNOWN_EXERCISE_STYLE)
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _present_currency(cls, value: object) -> object:
        if value is None:
            raise TermsRefusal(RefusalCode.UNKNOWN_CURRENCY)
        return value

    @field_validator("strike", mode="before")
    @classmethod
    def require_decimal(cls, value: object, info: ValidationInfo) -> Decimal:
        """Aceita strikes cuja escala pode ser preservada em texto decimal fixo ASCII."""
        if info.mode == "json":
            if not isinstance(value, str) or not _FIXED_DECIMAL.fullmatch(value):
                raise ValueError("strike JSON deve ser texto decimal fixo ASCII")
            value = Decimal(value)
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("strike deve ser Decimal finito")
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent > 0:
            raise ValueError("escala do strike com expoente positivo não cabe em decimal fixo")
        return value

    @field_serializer("strike", when_used="json")
    def _fixed_strike(self, value: Decimal) -> str:
        return format(value, "f")

    @model_validator(mode="after")
    def require_applicable_evidence(self) -> Self:
        """Confere a série, a data e a política declaradas contra a evidência apresentada."""
        doc = self.evidence
        if doc is None:
            if self.adjustment_policy != AdjustmentPolicy.UNKNOWN:
                raise ValueError("política conclusiva exige documento B3")
        elif (doc.symbol, doc.effective_on, doc.policy) != (
            self.symbol, self.effective_on, self.adjustment_policy
        ):
            raise ValueError("evidência incompatível com série, vigência ou política")
        return self
