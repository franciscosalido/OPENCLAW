"""Orcamento de requisicoes por credencial (DL-PR05): janelas deslizantes em memoria,
relogio sempre injetado. Nunca dorme: quem decide esperar e o chamador."""
from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.derivatives.oplab.errors import BudgetExceededError
from config.derivatives_config_model import Budget

ONE_SECOND = timedelta(seconds=1)
ONE_MINUTE = timedelta(minutes=1)

def credential_key(token: str) -> str:
    """Chave do orcamento: SHA-256 dos 8 primeiros caracteres; o token nunca e guardado."""
    return hashlib.sha256(token[:8].encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Fotografia do consumo nas duas janelas e do bloqueio vigente."""
    used_per_second: int
    used_per_minute: int
    blocked_until: datetime | None

class RequestBudget:
    """Limites ``per_second`` e ``per_minute`` de uma credencial, em memoria."""

    def __init__(self, cfg: Budget, *, key: str) -> None:
        """``key`` vem de ``credential_key``; uma instancia por credencial."""
        self.cfg = cfg
        self.key = key
        self._stamps: deque[datetime] = deque()
        self._blocked_until: datetime | None = None

    def _in_last_second(self, now: datetime) -> list[datetime]:
        while self._stamps and now - self._stamps[0] >= ONE_MINUTE:
            self._stamps.popleft()
        return [stamp for stamp in self._stamps if now - stamp < ONE_SECOND]

    def acquire(self, now: datetime) -> None:
        """Registra uma requisicao ou recusa sem dormir.

        Raises:
            BudgetExceededError: bloqueio vigente ou janela cheia; ``next_eligible_at``
                informa o primeiro instante em que uma nova tentativa cabe.
        """
        if self._blocked_until is not None and now < self._blocked_until:
            raise BudgetExceededError("orcamento bloqueado ate o instante informado",
                                      next_eligible_at=self._blocked_until)
        last_second = self._in_last_second(now)
        if len(last_second) >= self.cfg.per_second:
            raise BudgetExceededError("limite por segundo esgotado",
                                      next_eligible_at=last_second[0] + ONE_SECOND)
        if len(self._stamps) >= self.cfg.per_minute:
            raise BudgetExceededError("limite por minuto esgotado",
                                      next_eligible_at=self._stamps[0] + ONE_MINUTE)
        self._stamps.append(now)

    def block_until(self, when: datetime) -> None:
        """Honra ``Retry-After``: recusa tudo ate ``when``; um bloqueio nunca encurta."""
        if self._blocked_until is None or when > self._blocked_until:
            self._blocked_until = when

    def snapshot(self, now: datetime) -> BudgetSnapshot:
        """Consumo atual nas janelas deslizantes e bloqueio ainda vigente, se houver."""
        last_second = self._in_last_second(now)
        blocked = self._blocked_until
        if blocked is not None and now >= blocked:
            blocked = None
        return BudgetSnapshot(len(last_second), len(self._stamps), blocked)
