"""Transportes do cliente OpLab (DL-PR05): fixture agora, HTTP depois, mesmo contrato.
A procedencia e atribuida aqui, pelo adaptador; ``OPLAB_TOKEN`` so e lido neste modulo."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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
        name = f"{rendered.strip('/').replace('/', '_')}.json"
        try:
            payload = self._payload(name)
        except FileNotFoundError:
            raise NotFoundError("fixture ausente para a rota", status=404, route=rendered) from None
        return VendorResponse(200, payload, {}, now, rendered, self._provenance)

    def _payload(self, name: str) -> object:
        return json.loads((self._directory / name).read_bytes())

class HttpTransport:
    """Contrato HTTP em A: cliente isolado com MockTransport e ambiente de teste explícitos.

    Toda resposta daqui sai de um simulador em memoria, logo nasce ``REPLAY`` (proposito
    de teste). ``OBSERVED`` fica reservado a aquisicao homologada do estado B.
    """

    def __init__(
        self, cfg: Oplab, budget: RequestBudget, *, env: dict[str, str] | None = None,
        mock_transport: httpx.MockTransport | None = None,
    ) -> None:
        """Nao le o token nem abre rede na construcao.

        Raises:
            ValueError: ``max_retries`` diferente de zero (retry nao existe na Fase 1).
        """
        if budget.cfg.max_retries != 0:
            raise ValueError("max_retries deve ser 0: nao ha retry na Fase 1")
        self._cfg = cfg
        self._budget = budget
        self._env = env
        self._mock_transport = mock_transport

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        """Envia exatamente uma requisicao; todo erro vira ``OplabError`` sem o token."""
        rendered = render_route(route, **params)
        if (type(self._mock_transport) is not httpx.MockTransport or type(self._env) is not dict
                or forbid_network(self._env)):
            raise NetworkForbiddenError("rede proibida neste processo", route=rendered)
        url = str(self._cfg.base_url).rstrip("/") + rendered
        assert_allowed(url, ALLOWED_METHOD, self._cfg)
        token = self._env.get("OPLAB_TOKEN")
        if not token:
            raise AuthError("credencial OpLab ausente no ambiente", route=rendered)
        self._budget.acquire(now)
        client = httpx.AsyncClient(
            transport=self._mock_transport, timeout=self._budget.cfg.timeout_s,
            follow_redirects=False, trust_env=False,
        )
        client.headers[TOKEN_HEADER] = token
        failure: str | None = None
        try:
            async with client:
                response = await client.get(url, follow_redirects=False)
        except httpx.HTTPError as exc:
            failure = type(exc).__name__
        if failure is not None:
            raise TransportError(f"falha de transporte: {failure}", route=rendered)
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
        safe = {name: response.headers[name] for name in SAFE_HEADERS if name in response.headers}
        try:
            payload: object = response.json()
        except ValueError:
            pass
        else:
            return VendorResponse(status, payload, safe, now, rendered, Provenance.REPLAY)
        raise TransportError("corpo da resposta nao e JSON", status=status, route=rendered)
