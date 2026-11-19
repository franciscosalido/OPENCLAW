"""Taxonomia de erros do cliente OpLab (DL-PR05): credencial, assinatura, permissao,
limite e indisponibilidade sao distintos; a mensagem nunca carrega corpo nem headers."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

RATE_LIMIT_BLOCK_S = 300.0  # 429 sem Retry-After: bloqueio de 5 min publicado pela OpLab
UNAVAILABLE_BLOCK_S = 1.0  # 503 sem Retry-After: janela de 1 s do limite por segundo

class OplabError(Exception):
    """Erro tipado do cliente OpLab; ``message_safe`` nunca contem token, corpo ou headers."""

    def __init__(
        self, message_safe: str, *, status: int | None = None, route: str | None = None,
        retry_after_s: float | None = None, next_eligible_at: datetime | None = None,
    ) -> None:
        """Guarda apenas metadados seguros: status, rota e janela de nova tentativa."""
        super().__init__(message_safe)
        self.message_safe = message_safe
        self.status = status
        self.route = route
        self.retry_after_s = retry_after_s
        self.next_eligible_at = next_eligible_at

class ForbiddenRouteError(OplabError):
    """Rota, metodo ou parametro fora da allowlist; recusado antes de qualquer rede."""

class ForbiddenHostError(OplabError):
    """Esquema ou host diferente do aprovado, ou redirecionamento (3xx) nao aprovado."""

class AuthError(OplabError):
    """401, ou credencial ausente no ambiente (recusado antes de qualquer rede)."""

class SubscriptionError(OplabError):
    """402: assinatura ausente ou expirada."""

class PermissionError_(OplabError):
    """403: credencial sem permissao; o sufixo evita colidir com o builtin."""

class NotFoundError(OplabError):
    """404: recurso inexistente (ou fixture ausente no transporte de fixtures)."""

class RateLimitedError(OplabError):
    """429: limite por minuto estourado; carrega ``next_eligible_at``."""

class UnavailableError(OplabError):
    """503 e demais 5xx: indisponibilidade ou limite por segundo; sem retry automatico."""

class BudgetExceededError(OplabError):
    """Orcamento local esgotado ou bloqueado: recusado antes de qualquer rede."""

class TransportError(OplabError):
    """Timeout, falha de conexao ou corpo que nao e JSON."""

class NetworkForbiddenError(OplabError):
    """``QUIMERA_DERIV_FORBID_NETWORK=1``: o transporte HTTP esta proibido neste processo."""

_STATUS_ERRORS: dict[int, type[OplabError]] = {
    401: AuthError, 402: SubscriptionError, 403: PermissionError_, 404: NotFoundError,
    429: RateLimitedError, 503: UnavailableError,
}

def parse_retry_after(value: str | None, *, now: datetime) -> float | None:
    """Segundos pedidos por ``Retry-After`` (inteiro ou HTTP-date); ilegivel vira ``None``."""
    if value is None:
        return None
    text = value.strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)

def classify_status(
    status: int, *, retry_after: str | None, now: datetime, route: str,
) -> OplabError:
    """Mapeia um status HTTP de erro para a excecao tipada, sem levanta-la.

    429/503 sempre carregam ``next_eligible_at``: o ``Retry-After`` quando legivel,
    senao o bloqueio publicado (429: 5 min; 503: 1 s). Nenhum retry e feito aqui.
    """
    error_type = _STATUS_ERRORS.get(status)
    if error_type is None:
        error_type = UnavailableError if status >= 500 else OplabError
    wait_s: float | None = None
    if status in (429, 503):
        wait_s = parse_retry_after(retry_after, now=now)
        if wait_s is None:
            wait_s = RATE_LIMIT_BLOCK_S if status == 429 else UNAVAILABLE_BLOCK_S
    eligible = None if wait_s is None else now + timedelta(seconds=wait_s)
    return error_type(f"OpLab respondeu status {status}", status=status, route=route,
                      retry_after_s=wait_s, next_eligible_at=eligible)
