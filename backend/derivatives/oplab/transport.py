"""Transportes do cliente OpLab (DL-PR05): fixture agora, HTTP depois, mesmo contrato.
A procedencia e atribuida aqui, pelo adaptador; ``OPLAB_TOKEN`` so e lido neste modulo."""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx

from backend.derivatives.config import forbid_network
from backend.derivatives.oplab.budget import RequestBudget
from backend.derivatives.oplab.errors import (AuthError, ForbiddenHostError, NetworkForbiddenError,
    NotFoundError, TransportError, classify_status)
from backend.derivatives.oplab.routes import (ALLOWED_METHOD, MarketRoute, assert_allowed,
    render_route)
from backend.derivatives.provenance import Provenance
from config.derivatives_config_model import Oplab

SAFE_HEADERS = ("Retry-After", "Content-Type", "Date")
TOKEN_HEADER = "Access-Token"

@dataclass(frozen=True, slots=True)
class VendorResponse:
    """Resposta crua do fornecedor com procedencia atribuida pelo transporte."""
    status: int
    json: object
    headers_safe: Mapping[str, str]
    received_at: datetime
    route: str
    provenance: Provenance

class Transport(Protocol):
    """Contrato unico dos transportes: uma leitura GET de rota enumerada."""

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        """Le a rota com o relogio injetado ou levanta ``OplabError`` tipado."""
        ...

def redact(text: str, token: str | None) -> str:
    """Substitui o token por ``***`` em qualquer texto destinado a mensagem ou log."""
    return text.replace(token, "***") if token else text

class FixtureTransport:
    """Le fixtures JSON de um diretorio; nunca abre rede e nunca e ``OBSERVED``."""

    def __init__(
        self, directory: Path, *, provenance: Provenance | None = None,
        scripted: Sequence[tuple[int, str | None]] = (),
    ) -> None:
        """``scripted`` simula respostas ``(status, Retry-After)`` antes das fixtures.

        Raises:
            ValueError: tentativa de carimbar fixture como ``OBSERVED``.
        """
        inferred = Provenance.SYNTHETIC if directory.name == "synthetic" else Provenance.DOCUMENTAL
        self._provenance = inferred if provenance is None else provenance
        if self._provenance is Provenance.OBSERVED:
            raise ValueError("fixture nunca tem procedencia OBSERVED")
        self._directory = directory
        self._scripted = list(scripted)

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        """Resolve rota+parametros para ``<rota_com_underscores>.json`` no diretorio."""
        rendered = render_route(route, **params)
        if self._scripted:
            status, retry_after = self._scripted.pop(0)
            if status != 200:
                raise classify_status(status, retry_after=retry_after, now=now, route=rendered)
        path = self._directory / f"{rendered.strip('/').replace('/', '_')}.json"
        if not path.is_file():
            raise NotFoundError("fixture ausente para a rota", status=404, route=rendered)
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        return VendorResponse(200, payload, {}, now, rendered, self._provenance)

class HttpTransport:
    """GET HTTPS para a OpLab: allowlist, orcamento, sem redirecionamento e sem retry."""

    def __init__(
        self, cfg: Oplab, budget: RequestBudget, *, env: Mapping[str, str] | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        """Nao le o token nem abre rede na construcao.

        Raises:
            ValueError: ``max_retries`` diferente de zero (retry nao existe na Fase 1).
        """
        if budget.cfg.max_retries != 0:
            raise ValueError("max_retries deve ser 0: nao ha retry na Fase 1")
        self._cfg = cfg
        self._budget = budget
        self._env: Mapping[str, str] = os.environ if env is None else env
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(
            timeout=budget.cfg.timeout_s, follow_redirects=False))

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        """Envia exatamente uma requisicao; todo erro vira ``OplabError`` sem o token."""
        rendered = render_route(route, **params)
        if forbid_network(dict(self._env)):
            raise NetworkForbiddenError("rede proibida neste processo", route=rendered)
        url = str(self._cfg.base_url).rstrip("/") + rendered
        assert_allowed(url, ALLOWED_METHOD, self._cfg)
        token = self._env.get("OPLAB_TOKEN")
        if not token:
            raise AuthError("credencial OpLab ausente no ambiente", route=rendered)
        self._budget.acquire(now)
        client = self._client_factory()
        client.headers[TOKEN_HEADER] = token
        try:
            async with client:
                response = await client.get(url, follow_redirects=False)
        except httpx.HTTPError as exc:
            # ``from None``: a excecao httpx carrega a requisicao (e o header do token).
            raise TransportError(f"falha de transporte: {type(exc).__name__}",
                                 route=rendered) from None
        status = response.status_code
        if 300 <= status < 400:
            raise ForbiddenHostError("redirecionamento nao aprovado", status=status,
                                     route=rendered)
        if status != 200:
            error = classify_status(status, retry_after=response.headers.get("Retry-After"),
                                    now=now, route=rendered)
            if error.next_eligible_at is not None:
                self._budget.block_until(error.next_eligible_at)
            raise error
        try:
            payload: object = response.json()
        except ValueError:
            raise TransportError("corpo da resposta nao e JSON", status=status,
                                 route=rendered) from None
        safe = {name: response.headers[name] for name in SAFE_HEADERS if name in response.headers}
        return VendorResponse(status, payload, safe, now, rendered, Provenance.OBSERVED)
