"""Rascunhos e prévias imutáveis da boleta simulada."""
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, NamedTuple, Self

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, ValidationInfo,
    SerializerFunctionWrapHandler, computed_field, field_validator, model_serializer,
    model_validator,
)

from backend.derivatives.ticket.digest import digest


class _Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, revalidate_instances="always",
    )


class Side(StrEnum):
    """Sentido da perna."""

    BUY = "BUY"
    SELL = "SELL"


class Environment(StrEnum):
    """Ambiente admissível na fase D0."""

    SIMULATED = "SIMULATED"


def _cent_amount(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("dinheiro não finito")
    _, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    if exponent < -2 and any(digits[max(0, len(digits) + exponent + 2):]):
        raise ValueError("dinheiro fora do passo de 0,01")
    return value


def _exact_input(value: object, info: ValidationInfo) -> object:
    if isinstance(value, Decimal):
        return value
    if info.mode == "json" and isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("texto decimal inválido") from exc
    raise ValueError("esperado Decimal ou texto decimal em JSON")


Money = Annotated[Decimal, BeforeValidator(_exact_input), AfterValidator(_cent_amount)]
Text = Annotated[str, Field(min_length=1, pattern=r"^\S+$")]
PositiveInt = Annotated[int, Field(gt=0)]
Instant = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class CoverageGrant(_Frozen):
    """Quantidade máxima de uma série cedida pela boleta de origem."""

    series: Annotated[Text, AfterValidator(str.upper)]
    origin: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+$")]
    quantity: PositiveInt


class Leg(_Frozen):
    """Série, sentido, unidades e preço máximo de compra ou mínimo de venda."""

    symbol: Annotated[Text, AfterValidator(str.upper)]
    side: Side
    quantity: PositiveInt
    limit_price: Annotated[Money, Field(gt=0)]
    lot_size: PositiveInt

    @model_validator(mode="after")
    def _whole_lots(self) -> Self:
        if self.quantity % self.lot_size:
            raise ValueError("quantidade deve ser múltipla do lote")
        return self


class EditableField(StrEnum):
    """Campos operacionais editáveis pelo humano e sugeridos pelo mercado."""

    SYMBOL = "symbol"
    SIDE = "side"
    QUANTITY = "quantity"
    LIMIT_PRICE = "limit_price"
    NET_LIMIT = "net_limit"
    SEND_DEADLINE = "send_deadline"
    ORDER_VALIDITY = "order_validity"


_LEG_FIELDS = {EditableField.SYMBOL, EditableField.SIDE, EditableField.QUANTITY,
               EditableField.LIMIT_PRICE}


class FieldRef(NamedTuple):
    """Identifica um campo do conjunto ou de uma perna pela posição na boleta."""

    field: EditableField
    leg_index: Annotated[int, Field(ge=0, lt=4)] | None = None

class _Ticket(_Frozen):
    environment: Environment = Environment.SIMULATED
    legs: Annotated[tuple[Leg, ...], Field(min_length=1, max_length=4)]
    net_limit: Money  # Débito máximo positivo, crédito mínimo negativo.
    gross_cap: Annotated[Money, Field(ge=0)]
    send_deadline: Instant
    order_validity: Instant
    quote_snapshot_id: Text
    version: PositiveInt = 1
    coverage: Annotated[tuple[CoverageGrant, ...], Field(max_length=4)] = ()

    @field_validator("coverage", mode="after")
    @classmethod
    def _ordered_grants(cls, grants: tuple[CoverageGrant, ...]) -> tuple[CoverageGrant, ...]:
        return tuple(sorted(grants, key=lambda grant: (grant.series, grant.origin)))

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Mantém o corpo histórico dos recibos sem autorização."""
        fields: dict[str, object] = handler(self)
        if not self.coverage:
            fields.pop("coverage", None)
        return fields

    @model_validator(mode="after")
    def _distinct_symbols_and_grants(self) -> Self:
        if len({leg.symbol for leg in self.legs}) != len(self.legs):
            raise ValueError("série duplicada")
        if len({(g.series, g.origin) for g in self.coverage}) != len(self.coverage):
            raise ValueError("autorização de cobertura duplicada")
        return self


class TicketDraft(_Ticket):
    """Proposta versionada com travas de edição individuais por campo."""

    locked: frozenset[FieldRef] = frozenset()

    @model_validator(mode="after")
    def _existing_leg(self) -> Self:
        for ref in self.locked:
            self.check_field(ref)
        return self

    def check_field(self, ref: FieldRef) -> None:
        """Valida a referência e a existência da perna nesta versão."""
        if not isinstance(ref, FieldRef) or type(ref.field) is not EditableField:
            raise ValueError("campo inválido")
        if (ref.leg_index is not None) != (ref.field in _LEG_FIELDS):
            raise ValueError("índice exigido somente para campo da perna")
        if ref.leg_index is not None and (type(ref.leg_index) is not int
                                          or not 0 <= ref.leg_index < len(self.legs)):
            raise ValueError("perna ausente")


class Preview(_Ticket):
    """Conteúdo de aprovação e exposição parcial fornecida pelo chamador."""

    partial_exposure: Annotated[Money, Field(ge=0)]

    @classmethod
    def from_draft(cls, draft: TicketDraft, *, partial_exposure: Decimal) -> Self:
        """Valida os valores da versão exibida, excluindo metadados de edição."""
        values = dict(TicketDraft.model_validate(draft))
        del values["locked"]
        return cls.model_validate(values | {"partial_exposure": partial_exposure})

    @computed_field  # type: ignore[prop-decorator]
    @property
    def digest(self) -> str:
        """Resumo derivado do conteúdo, independente do contador de versão."""
        return digest(self)


def _updated(draft: TicketDraft, changes: Mapping[FieldRef, object],
             **metadata: object) -> TicketDraft:
    values = dict(draft)
    legs = [dict(leg) for leg in draft.legs]
    for ref, value in changes.items():
        draft.check_field(ref)
        fields = values if ref.leg_index is None else legs[ref.leg_index]
        fields[ref.field.value] = value
    return TicketDraft.model_validate(values | {"legs": tuple(legs)} | metadata)


def apply_human_edit(draft: TicketDraft, field: FieldRef, value: object) -> TicketDraft:
    """Aplica e valida uma edição, trava o campo e incrementa a versão."""
    return _updated(draft, {field: value}, locked=draft.locked | {field}, version=draft.version + 1)


class MarketSuggestion(NamedTuple):
    """Foto de origem e alterações candidatas a uma atualização atômica."""

    quote_snapshot_id: str
    changes: Mapping[FieldRef, object]


def apply_market_refresh(draft: TicketDraft, suggestion: MarketSuggestion) -> TicketDraft:
    """Adota a foto somente ao incorporar uma mudança autorizável, num único incremento."""
    changes = {ref: value for ref, value in suggestion.changes.items() if ref not in draft.locked}
    updated = _updated(draft, changes)
    if updated == draft:
        return draft
    return TicketDraft.model_validate(dict(updated) | {
        "quote_snapshot_id": suggestion.quote_snapshot_id, "version": draft.version + 1,
    })


def unlock(draft: TicketDraft, field: FieldRef) -> TicketDraft:
    """Retira a trava de edição sem alterar o conteúdo autorizável."""
    draft.check_field(field)
    return TicketDraft.model_validate(dict(draft) | {"locked": draft.locked - {field}})
