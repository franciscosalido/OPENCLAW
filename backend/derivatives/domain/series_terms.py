"""Termos vigentes por série (DL2-PR01), independentes da chain da Fase 01."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
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


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TERMS_CONFIG = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always")


def _input_mapping(data: object) -> dict[str, object]:
    if not isinstance(data, Mapping):
        raise ValueError("termos e evidências exigem um mapping ou objeto JSON")
    return dict(data)


def _json_date(value: object, info: ValidationInfo) -> object:
    if info.mode == "json" and isinstance(value, str):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("data JSON deve estar no formato AAAA-MM-DD")
        return parsed
    return value


_CivilDate = Annotated[date, BeforeValidator(_json_date)]


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

    issuer: Literal["B3"]
    document: Text
    version: Text
    published_on: _CivilDate
    symbol: Text
    effective_on: _CivilDate
    policy: AdjustmentPolicy
    _require_mapping = model_validator(mode="before")(_input_mapping)


class SeriesTerms(_TermsModel):
    """Uma observação por série e data de vigência explícita.

    FATCOT admite neste recorte cotação por unidade (1) ou por mil (1000),
    conforme o layout COTAHIST rev. 02, p. 6. O lote tem fonte própria.
    """

    symbol: Text
    effective_on: _CivilDate
    source: Text
    strike: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    contract_size: Annotated[int, Field(gt=0)]
    quotation_form: Literal[1, 1000]
    currency: Literal["BRL"]
    exercise_style: ExerciseStyle
    adjustment_policy: AdjustmentPolicy
    evidence: AdjustmentEvidence | None = None

    @model_validator(mode="before")
    @classmethod
    def require_series_fields(cls, data: object, info: ValidationInfo) -> object:
        """Recusa faltas na ordem lote, fator, estilo e moeda antes de validar os valores."""
        fields = _input_mapping(data)
        if fields.get("contract_size") is None:
            raise TermsRefusal(RefusalCode.MISSING_CONTRACT_SIZE)
        if fields.get("quotation_form") is None:
            raise TermsRefusal(RefusalCode.MISSING_QUOTATION_FORM)
        style = fields.get("exercise_style")
        if style is None or style is ExerciseStyle.UNKNOWN or (
            info.mode == "json" and style == ExerciseStyle.UNKNOWN.value
        ):
            raise TermsRefusal(RefusalCode.UNKNOWN_EXERCISE_STYLE)
        if fields.get("currency") is None:
            raise TermsRefusal(RefusalCode.UNKNOWN_CURRENCY)
        return fields

    @field_validator("quotation_form", mode="before")
    @classmethod
    def _integer_factor(cls, value: object) -> object:
        # Literal[1, 1000] também compara por igualdade com True e números de ponto flutuante.
        if type(value) is not int:
            raise ValueError("FATCOT deve ser inteiro")
        return value

    @field_validator("strike", mode="before")
    @classmethod
    def require_decimal(cls, value: object, info: ValidationInfo) -> Decimal:
        """Lê o texto decimal em JSON ou um Decimal em Python e preserva a precisão."""
        if info.mode == "json" and isinstance(value, str):
            try:
                value = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("strike JSON deve conter um decimal") from exc
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("strike deve ser Decimal finito")
        return value

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
