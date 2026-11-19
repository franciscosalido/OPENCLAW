"""DL-PR05b: transportes OpLab sem rede — ``httpx.MockTransport`` e fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from backend.derivatives.oplab.budget import RequestBudget, credential_key
from backend.derivatives.oplab.errors import (
    AuthError,
    BudgetExceededError,
    ForbiddenHostError,
    ForbiddenRouteError,
    NetworkForbiddenError,
    NotFoundError,
    OplabError,
    PermissionError_,
    RateLimitedError,
    SubscriptionError,
    TransportError,
    UnavailableError,
)
from backend.derivatives.oplab.routes import MarketRoute
from backend.derivatives.oplab.transport import (
    SAFE_HEADERS,
    FixtureTransport,
    HttpTransport,
    Transport,
    redact,
)
from backend.derivatives.provenance import Provenance
from config.derivatives_config_model import Budget, Oplab

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
TOKEN = "test-token-not-real"
ENV = {"OPLAB_TOKEN": TOKEN}
DOCUMENTAL = Path("tests/fixtures/derivatives/documental")
Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Handler de ``MockTransport`` que conta e guarda as requisicoes recebidas."""

    def __init__(self, respond: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)


def _json(status: int = 200, payload: object = None, **headers: str) -> Handler:
    body = {"market_status": "N"} if payload is None else payload
    return lambda _request: httpx.Response(status, json=body, headers=headers)


def _http(
    recorder: Recorder, *, env: dict[str, str] | None = None, cfg: Oplab | None = None,
    budget: Budget | None = None,
) -> HttpTransport:
    request_budget = RequestBudget(budget or Budget(), key=credential_key(TOKEN))
    return HttpTransport(
        cfg or Oplab(), request_budget, env=ENV if env is None else env,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
    )


async def _status(transport: Transport) -> object:
    return await transport.get(MarketRoute.MARKET_STATUS, params={}, now=NOW)


def _assert_no_token(error: BaseException) -> None:
    assert TOKEN not in str(error)
    assert TOKEN not in repr(error)
    assert TOKEN not in repr(vars(error))
    assert error.__cause__ is None


async def test_success_sends_one_get_with_the_token_header_only() -> None:
    recorder = Recorder(_json(200, {"market_status": "N"}, **{"Set-Cookie": "s=1",
                                                              "Date": "now"}))
    response = await _http(recorder).get(MarketRoute.STOCK, params={"symbol": "PETR4"},
                                         now=NOW)
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "GET"
    assert str(request.url) == "https://api.oplab.com.br/v3/market/stocks/PETR4"
    assert request.headers["Access-Token"] == TOKEN
    assert request.url.query == b""
    assert response.status == 200
    assert response.json == {"market_status": "N"}
    assert response.provenance is Provenance.OBSERVED
    assert response.received_at == NOW
    assert response.route == "/market/stocks/PETR4"
    assert set(response.headers_safe) <= set(SAFE_HEADERS)
    assert "Set-Cookie" not in response.headers_safe
    assert response.headers_safe["Date"] == "now"


async def test_other_host_is_refused_before_any_request() -> None:
    recorder = Recorder(_json())
    transport = _http(recorder, cfg=Oplab.model_validate({"base_url": "https://evil.example/v3"}))
    with pytest.raises(ForbiddenHostError) as refused:
        await _status(transport)
    assert recorder.requests == []
    _assert_no_token(refused.value)


async def test_yaml_restricted_route_is_refused_before_any_request() -> None:
    recorder = Recorder(_json())
    transport = _http(recorder, cfg=Oplab(allowed_routes=["/market/stocks/{symbol}"]))
    with pytest.raises(ForbiddenRouteError):
        await _status(transport)
    assert recorder.requests == []


async def test_invalid_symbol_is_refused_before_any_request() -> None:
    recorder = Recorder(_json())
    with pytest.raises(ForbiddenRouteError):
        await _http(recorder).get(MarketRoute.STOCK, params={"symbol": "PETR4/../x"}, now=NOW)
    assert recorder.requests == []


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_redirect_is_never_followed(status: int) -> None:
    recorder = Recorder(lambda _r: httpx.Response(
        status, headers={"Location": "https://evil.example/v3/market/status"}))
    with pytest.raises(ForbiddenHostError) as refused:
        await _status(_http(recorder))
    assert len(recorder.requests) == 1
    assert refused.value.status == status
    _assert_no_token(refused.value)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, AuthError), (402, SubscriptionError), (403, PermissionError_),
     (404, NotFoundError), (500, UnavailableError), (418, OplabError)],
)
async def test_error_status_maps_to_typed_error_without_body(
    status: int, expected: type[OplabError],
) -> None:
    recorder = Recorder(_json(status, {"error": "corpo-bruto-do-fornecedor"}))
    with pytest.raises(expected) as raised:
        await _status(_http(recorder))
    assert type(raised.value) is expected
    assert "corpo-bruto" not in str(raised.value)
    assert len(recorder.requests) == 1
    _assert_no_token(raised.value)


async def test_503_is_sent_exactly_once_and_blocks_the_budget() -> None:
    recorder = Recorder(_json(503))
    transport = _http(recorder)
    with pytest.raises(UnavailableError) as unavailable:
        await _status(transport)
    assert len(recorder.requests) == 1
    assert unavailable.value.next_eligible_at == NOW + timedelta(seconds=1)
    with pytest.raises(BudgetExceededError) as blocked:
        await _status(transport)
    assert len(recorder.requests) == 1
    assert blocked.value.next_eligible_at == NOW + timedelta(seconds=1)


async def test_429_retry_after_is_honoured_without_retry() -> None:
    recorder = Recorder(_json(429, **{"Retry-After": "120"}))
    transport = _http(recorder)
    with pytest.raises(RateLimitedError) as limited:
        await _status(transport)
    assert limited.value.retry_after_s == 120.0
    assert limited.value.next_eligible_at == NOW + timedelta(seconds=120)
    with pytest.raises(BudgetExceededError):
        await transport.get(MarketRoute.MARKET_STATUS, params={},
                            now=NOW + timedelta(seconds=119))
    assert len(recorder.requests) == 1


async def test_network_forbidden_flag_wins_before_token_and_request() -> None:
    recorder = Recorder(_json())
    transport = _http(recorder, env={**ENV, "QUIMERA_DERIV_FORBID_NETWORK": "1"})
    with pytest.raises(NetworkForbiddenError) as refused:
        await _status(transport)
    assert recorder.requests == []
    _assert_no_token(refused.value)


@pytest.mark.parametrize("env", [{}, {"OPLAB_TOKEN": ""}])
async def test_missing_token_is_an_auth_error_before_any_request(env: dict[str, str]) -> None:
    recorder = Recorder(_json())
    with pytest.raises(AuthError) as refused:
        await _status(_http(recorder, env=env))
    assert recorder.requests == []
    assert refused.value.status is None


async def test_local_budget_refuses_before_any_request() -> None:
    recorder = Recorder(_json())
    transport = _http(recorder, budget=Budget(per_second=1))
    await _status(transport)
    with pytest.raises(BudgetExceededError):
        await _status(transport)
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout("t"), httpx.ConnectError("c"), httpx.ConnectTimeout("ct")],
)
async def test_httpx_failure_becomes_transport_error_without_request(
    failure: httpx.HTTPError,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        failure.request = request
        raise failure

    recorder = Recorder(explode)
    with pytest.raises(TransportError) as raised:
        await _status(_http(recorder))
    assert len(recorder.requests) == 1
    assert type(failure).__name__ in raised.value.message_safe
    assert "api.oplab.com.br" not in raised.value.message_safe
    assert raised.value.route == "/market/status"
    _assert_no_token(raised.value)


async def test_non_json_body_is_a_transport_error() -> None:
    recorder = Recorder(lambda _r: httpx.Response(200, text="<html>manutencao</html>"))
    with pytest.raises(TransportError) as raised:
        await _status(_http(recorder))
    assert "manutencao" not in str(raised.value)
    _assert_no_token(raised.value)


def test_transport_repr_and_state_never_hold_the_token() -> None:
    budget = RequestBudget(Budget(), key=credential_key(TOKEN))
    transport = HttpTransport(Oplab(), budget, env={})
    assert TOKEN not in repr(transport)
    holder = HttpTransport(Oplab(), budget, env=ENV)
    slots = {name: value for name, value in vars(holder).items() if name != "_env"}
    assert TOKEN not in repr(slots)


def test_retries_are_refused_at_construction() -> None:
    budget = RequestBudget(Budget(max_retries=1), key=credential_key(TOKEN))
    with pytest.raises(ValueError, match="max_retries"):
        HttpTransport(Oplab(), budget, env=ENV)


async def test_default_client_never_follows_redirects_and_uses_the_yaml_timeout() -> None:
    budget = RequestBudget(Budget(timeout_s=3.5), key=credential_key(TOKEN))
    transport = HttpTransport(Oplab(), budget, env=ENV)
    client = transport._client_factory()  # inspecao do default do construtor
    try:
        assert client.follow_redirects is False
        assert client.timeout == httpx.Timeout(3.5)
    finally:
        await client.aclose()


async def test_default_environment_flag_blocks_real_transport() -> None:
    budget = RequestBudget(Budget(), key=credential_key(TOKEN))
    transport = HttpTransport(Oplab(), budget)
    with pytest.raises(NetworkForbiddenError):
        await _status(transport)


@pytest.mark.parametrize(
    ("route", "params", "name"),
    [
        (MarketRoute.OPTIONS_CHAIN, {"symbol": "PETR3"}, "market_options_PETR3.json"),
        (MarketRoute.STOCK, {"symbol": "PETR4"}, "market_stocks_PETR4.json"),
        (MarketRoute.INTEREST_RATES, {}, "market_interest_rates.json"),
        (MarketRoute.MARKET_STATUS, {}, "market_status.json"),
    ],
)
async def test_fixture_transport_resolves_the_documental_files(
    route: MarketRoute, params: dict[str, str], name: str,
) -> None:
    response = await FixtureTransport(DOCUMENTAL).get(route, params=params, now=NOW)
    assert response.json == json.loads((DOCUMENTAL / name).read_text(encoding="utf-8"))
    assert response.provenance is Provenance.DOCUMENTAL
    assert response.status == 200
    assert response.received_at == NOW
    assert response.headers_safe == {}


async def test_fixture_provenance_is_never_observed(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic"
    synthetic.mkdir()
    (synthetic / "market_status.json").write_text('{"market_status": "A"}', encoding="utf-8")
    response = await _status_of(FixtureTransport(synthetic))
    assert response.provenance is Provenance.SYNTHETIC
    replay = await _status_of(FixtureTransport(synthetic, provenance=Provenance.REPLAY))
    assert replay.provenance is Provenance.REPLAY
    with pytest.raises(ValueError, match="OBSERVED"):
        FixtureTransport(synthetic, provenance=Provenance.OBSERVED)


async def _status_of(transport: FixtureTransport) -> object:
    return await transport.get(MarketRoute.MARKET_STATUS, params={}, now=NOW)


async def test_fixture_missing_file_is_not_found_without_leaking_the_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(NotFoundError) as missing:
        await FixtureTransport(tmp_path).get(MarketRoute.STOCK, params={"symbol": "VALE3"},
                                             now=NOW)
    assert missing.value.route == "/market/stocks/VALE3"
    assert str(tmp_path) not in missing.value.message_safe


async def test_fixture_scripted_responses_come_first_and_in_order() -> None:
    transport = FixtureTransport(DOCUMENTAL, scripted=[(429, None), (503, "7"), (200, None)])
    with pytest.raises(RateLimitedError) as limited:
        await _status_of(transport)
    assert limited.value.next_eligible_at == NOW + timedelta(seconds=300)
    with pytest.raises(UnavailableError) as unavailable:
        await _status_of(transport)
    assert unavailable.value.next_eligible_at == NOW + timedelta(seconds=7)
    assert (await _status_of(transport)).status == 200
    assert (await _status_of(transport)).status == 200


async def test_fixture_transport_refuses_invalid_symbols() -> None:
    with pytest.raises(ForbiddenRouteError):
        await FixtureTransport(DOCUMENTAL).get(MarketRoute.STOCK,
                                               params={"symbol": "../manifest"}, now=NOW)


def test_redact_replaces_every_occurrence_and_tolerates_absence() -> None:
    assert redact(f"a {TOKEN} b {TOKEN}", TOKEN) == "a *** b ***"
    assert redact("sem segredo", TOKEN) == "sem segredo"
    assert redact("texto", None) == "texto"
    assert redact("texto", "") == "texto"
