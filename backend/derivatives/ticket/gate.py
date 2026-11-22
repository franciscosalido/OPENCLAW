"""Emissão e consumo local de decisões humanas no simulador."""
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import ValidationError, model_validator

from backend.derivatives.ticket.models import Instant, PositiveInt, Preview, Text, _Frozen


class Action(StrEnum):
    """Ações que exigem uma decisão explícita."""
    EXECUTE = "EXECUTE"
    CANCEL_ORDER = "CANCEL_ORDER"
    ARM = "ARM"
    DISARM = "DISARM"
    DISCARD = "DISCARD"
    RESUME = "RESUME"


class DecisionRefusal(ValueError):
    """Falha de emissão, vínculo ou consumo."""


class HumanDecision(_Frozen):
    """Decisão imutável vinculada a uma ação e uma boleta."""
    action: Action
    ticket: Text
    nonce: Text
    issued_at: Instant
    expires_at: Instant
    digest: Text | None = None
    version: PositiveInt | None = None
    order_id: Text | None = None
    spec_digest: Text | None = None

    @model_validator(mode="after")
    def _bindings(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise DecisionRefusal("tempo inválido")
        preview = self.action in (Action.ARM, Action.EXECUTE)
        for value, required in ((self.digest, preview), (self.version, preview),
                                (self.order_id, self.action == Action.CANCEL_ORDER),
                                (self.spec_digest, self.action == Action.ARM)):
            if required and value is None:
                raise DecisionRefusal("vínculo ausente")
            if not required and value is not None:
                raise DecisionRefusal("vínculo indevido")
        return self


def issue(action: Action, *, ticket: str, nonce: str, issued_at: datetime, expires_at: datetime,
          preview: Preview | None = None, order_id: str | None = None,
          spec_digest: str | None = None) -> HumanDecision:
    """Emite a decisão com os vínculos exigidos pela ação."""
    if not ticket or not nonce:
        raise DecisionRefusal("identidade ausente")
    if issued_at.utcoffset() is None or expires_at.utcoffset() is None:
        raise DecisionRefusal("tempo inválido")
    try:
        return HumanDecision(action=action, ticket=ticket, nonce=nonce, issued_at=issued_at,
                             expires_at=expires_at, digest=preview.digest if preview else None,
                             version=preview.version if preview else None, order_id=order_id,
                             spec_digest=spec_digest)
    except ValidationError as exc:
        cause = (exc.errors()[0].get("ctx") or {}).get("error")
        raise DecisionRefusal(str(cause or exc)) from exc


class DecisionLedger:
    """Consumo único de cada nonce dentro do livro da sessão."""
    def __init__(self) -> None:
        self._used: dict[str, object] = {}

    def consume(self, decision: HumanDecision, *, action: Action, ticket: str, now: datetime,
                preview: Preview | None = None, order_id: str | None = None,
                spec_digest: str | None = None) -> None:
        """Valida na ordem do contrato; insere o nonce somente após todos os vínculos."""
        if type(decision) is not HumanDecision:
            raise DecisionRefusal("decisão inválida")
        try:
            decision = HumanDecision.model_validate(decision)
        except ValidationError as exc:
            raise DecisionRefusal("decisão inválida") from exc
        if decision.action != action:
            raise DecisionRefusal("ação divergente")
        if decision.ticket != ticket:
            raise DecisionRefusal("boleta divergente")
        if now.utcoffset() is None:
            raise DecisionRefusal("tempo inválido")
        instant = now.astimezone(UTC)
        if instant < decision.issued_at:
            raise DecisionRefusal("decisão ainda não válida")
        if instant > decision.expires_at:
            raise DecisionRefusal("decisão vencida")
        if decision.nonce in self._used:
            raise DecisionRefusal("decisão já usada")
        if decision.digest != (preview.digest if preview else None):
            raise DecisionRefusal("resumo divergente")
        if decision.version != (preview.version if preview else None):
            raise DecisionRefusal("versão divergente")
        if decision.order_id != order_id:
            raise DecisionRefusal("ordem divergente")
        if decision.spec_digest != spec_digest:
            raise DecisionRefusal("gatilho divergente")
        marker = object()
        if self._used.setdefault(decision.nonce, marker) is not marker:
            raise DecisionRefusal("decisão já usada")
