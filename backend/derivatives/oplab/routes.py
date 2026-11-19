"""Allowlist positiva de rotas Market da OpLab v3 (DL-PR05): somente GET, somente HTTPS,
host exato e rotas enumeradas. O YAML pode restringir a lista, nunca amplia-la."""
from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from backend.derivatives.oplab.errors import ForbiddenHostError, ForbiddenRouteError
from config.derivatives_config_model import Oplab

ALLOWED_METHOD = "GET"
ALLOWED_SCHEME = "https"
ALLOWED_HOST = "api.oplab.com.br"
BASE_PATH = "/v3"
SYMBOL_PATTERN = "[A-Z0-9]{4,12}"
FORBIDDEN_SEGMENTS = frozenset({"domain"})  # dominio de ordens: o mesmo token o opera

class MarketRoute(StrEnum):
    """Rotas de leitura de mercado autorizadas na Fase 1 (ADR-0023, decisao 5)."""
    OPTIONS_CHAIN = "/market/options/{symbol}"
    STOCK = "/market/stocks/{symbol}"
    INTEREST_RATES = "/market/interest_rates"
    MARKET_STATUS = "/market/status"

_ROUTE_PATTERNS: dict[MarketRoute, re.Pattern[str]] = {
    route: re.compile(re.escape(route.value).replace(re.escape("{symbol}"), SYMBOL_PATTERN))
    for route in MarketRoute
}

def render_route(route: MarketRoute, **params: str) -> str:
    """Renderiza a rota com parametros validados; qualquer desvio e recusado.

    Raises:
        ForbiddenRouteError: parametro ausente, desconhecido ou ``symbol`` fora de
            ``[A-Z0-9]{4,12}`` (sem ``/``, ``?``, ``..`` nem minusculas).
    """
    expected = {"symbol"} if "{symbol}" in route.value else set()
    if set(params) != expected:
        raise ForbiddenRouteError("parametros de rota fora do contrato", route=route.value)
    if not expected:
        return route.value
    symbol = params["symbol"]
    if re.fullmatch(SYMBOL_PATTERN, symbol) is None:
        raise ForbiddenRouteError("symbol fora do formato permitido", route=route.value)
    return route.value.format(symbol=symbol)

def assert_allowed(url: str, method: str, cfg: Oplab) -> None:
    """Exige GET, HTTPS, host exato, prefixo ``/v3`` e rota enumerada, sem query.

    A rota precisa pertencer a ``MarketRoute`` **e** a ``cfg.allowed_routes`` (dupla
    lista). Deve ser chamada antes de qualquer envio; nada aqui toca a rede.

    Raises:
        ForbiddenHostError: esquema ou host (inclusive porta/userinfo) nao aprovado.
        ForbiddenRouteError: metodo, prefixo, query, fragmento ou rota nao aprovados.
    """
    parts = urlsplit(url)
    if parts.scheme != ALLOWED_SCHEME or parts.netloc != ALLOWED_HOST:
        raise ForbiddenHostError("esquema ou host nao aprovado")
    if method != ALLOWED_METHOD:
        raise ForbiddenRouteError("metodo nao permitido: somente GET")
    if parts.query or parts.fragment or "?" in url or "#" in url:
        raise ForbiddenRouteError("query string e fragmento sao proibidos")
    if not parts.path.startswith(f"{BASE_PATH}/"):
        raise ForbiddenRouteError("caminho fora do prefixo da API aprovada")
    path = parts.path[len(BASE_PATH):]
    if FORBIDDEN_SEGMENTS.intersection(path.lower().split("/")):
        raise ForbiddenRouteError("dominio de ordens e proibido no Laboratorio")
    for route, pattern in _ROUTE_PATTERNS.items():
        if route.value in cfg.allowed_routes and pattern.fullmatch(path) is not None:
            return
    raise ForbiddenRouteError("rota fora da allowlist enumerada")
