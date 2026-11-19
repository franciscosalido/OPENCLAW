"""DL-PR05a: allowlist positiva de rotas OpLab — nada fora do enumerado passa."""

from __future__ import annotations

import pytest

from backend.derivatives.oplab.errors import ForbiddenHostError, ForbiddenRouteError
from backend.derivatives.oplab.routes import (
    ALLOWED_HOST,
    ALLOWED_METHOD,
    BASE_PATH,
    MarketRoute,
    assert_allowed,
    render_route,
)
from config.derivatives_config_model import Oplab

CFG = Oplab()
BASE = f"https://{ALLOWED_HOST}{BASE_PATH}"
GOOD_PATHS = (
    "/market/options/PETR3",
    "/market/stocks/PETR4",
    "/market/interest_rates",
    "/market/status",
)


def test_constants_are_the_approved_endpoint() -> None:
    assert (ALLOWED_METHOD, ALLOWED_HOST, BASE_PATH) == ("GET", "api.oplab.com.br", "/v3")
    assert str(CFG.base_url).rstrip("/") == BASE


@pytest.mark.parametrize(
    ("route", "params", "expected"),
    [
        (MarketRoute.OPTIONS_CHAIN, {"symbol": "PETR3"}, "/market/options/PETR3"),
        (MarketRoute.STOCK, {"symbol": "BOVA11"}, "/market/stocks/BOVA11"),
        (MarketRoute.INTEREST_RATES, {}, "/market/interest_rates"),
        (MarketRoute.MARKET_STATUS, {}, "/market/status"),
    ],
)
def test_every_market_route_renders(
    route: MarketRoute, params: dict[str, str], expected: str,
) -> None:
    assert render_route(route, **params) == expected


def test_enum_and_default_yaml_allowlist_are_the_same_four_routes() -> None:
    assert sorted(route.value for route in MarketRoute) == sorted(CFG.allowed_routes)
    assert len(MarketRoute) == 4


@pytest.mark.parametrize(
    "symbol",
    ["petr4", "PETR4/..", "PETR4?x=1", "A" * 13, "ABC", "", "PETR 4", "PETR4\n",
     "../PETR4", "PETR4#x", "PETR4%2F", "PÉTR4"],
)
def test_invalid_symbol_is_refused(symbol: str) -> None:
    with pytest.raises(ForbiddenRouteError):
        render_route(MarketRoute.OPTIONS_CHAIN, symbol=symbol)


def test_unknown_missing_or_unexpected_params_are_refused() -> None:
    with pytest.raises(ForbiddenRouteError):
        render_route(MarketRoute.STOCK, symbol="PETR4", extra="x")
    with pytest.raises(ForbiddenRouteError):
        render_route(MarketRoute.STOCK)
    with pytest.raises(ForbiddenRouteError):
        render_route(MarketRoute.MARKET_STATUS, symbol="PETR4")
    with pytest.raises(ForbiddenRouteError):
        render_route(MarketRoute.OPTIONS_CHAIN, underlying="PETR4")


@pytest.mark.parametrize("path", GOOD_PATHS)
def test_the_four_enumerated_urls_are_allowed(path: str) -> None:
    assert_allowed(BASE + path, "GET", CFG)


@pytest.mark.parametrize(
    "url",
    [
        f"http://{ALLOWED_HOST}/v3/market/status",
        "https://api.oplab.com.br.evil/v3/market/status",
        "https://evil.api.oplab.com.br/v3/market/status",
        "https://api.oplab.com.br@evil.example/v3/market/status",
        "https://user:pw@api.oplab.com.br/v3/market/status",
        "https://api.oplab.com.br:8443/v3/market/status",
        "https://API.OPLAB.COM.BR/v3/market/status",
        "ftp://api.oplab.com.br/v3/market/status",
        "//api.oplab.com.br/v3/market/status",
    ],
)
def test_wrong_scheme_or_host_is_refused_as_host_error(url: str) -> None:
    with pytest.raises(ForbiddenHostError):
        assert_allowed(url, "GET", CFG)


@pytest.mark.parametrize(
    "path",
    [
        "/v2/market/status",
        "/market/status",
        "/v3",
        "/v3/",
        "/v3/domain/portfolios",
        "/v3/DOMAIN/portfolios",
        "/v3/domain/orders",
        "/v3/market/options/PETR4/domain",
        "/v3/market/domain",
        "/v3/market/options/bs",
        "/v3/market/options/details/PETRE100",
        "/v3/market/options/strategies/covered",
        "/v3/market/instruments/XBOV11",
        "/v3/market/status/",
        "/v3/market/status/extra",
        "/v3//market/status",
        "/v3/market/../domain/orders",
        "/v3/market/options/petr4",
        "/v3/market/stocks/PETR4%2F..",
        "/v3/market/status?x=1",
        "/v3/market/status?access_token=abc",
        "/v3/market/status?",
        "/v3/market/status#frag",
        "/v3/market/stocks/PETR4?next=/domain/orders",
    ],
)
def test_everything_outside_the_enumerated_routes_is_refused(path: str) -> None:
    with pytest.raises(ForbiddenRouteError):
        assert_allowed(f"https://{ALLOWED_HOST}{path}", "GET", CFG)


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "HEAD", "get", ""])
def test_any_method_other_than_get_is_refused(method: str) -> None:
    with pytest.raises(ForbiddenRouteError):
        assert_allowed(BASE + "/market/status", method, CFG)


def test_yaml_cannot_widen_the_allowlist_beyond_the_enum() -> None:
    widened = Oplab(allowed_routes=[*CFG.allowed_routes, "/market/options/bs",
                                    "/market/instruments/{symbol}"])
    with pytest.raises(ForbiddenRouteError):
        assert_allowed(BASE + "/market/options/bs", "GET", widened)
    with pytest.raises(ForbiddenRouteError):
        assert_allowed(BASE + "/market/instruments/XBOV11", "GET", widened)
    assert_allowed(BASE + "/market/status", "GET", widened)


def test_yaml_can_restrict_the_allowlist() -> None:
    restricted = Oplab(allowed_routes=["/market/status"])
    assert_allowed(BASE + "/market/status", "GET", restricted)
    for path in GOOD_PATHS[:3]:
        with pytest.raises(ForbiddenRouteError):
            assert_allowed(BASE + path, "GET", restricted)


def test_refusal_messages_never_echo_the_url() -> None:
    secret_url = "https://evil.example/v3/market/status?access_token=SEGREDO"
    with pytest.raises(ForbiddenHostError) as host_error:
        assert_allowed(secret_url, "GET", CFG)
    assert "SEGREDO" not in str(host_error.value)
    with pytest.raises(ForbiddenRouteError) as route_error:
        assert_allowed(BASE + "/market/status?access_token=SEGREDO", "GET", CFG)
    assert "SEGREDO" not in str(route_error.value)
    assert "SEGREDO" not in route_error.value.message_safe
