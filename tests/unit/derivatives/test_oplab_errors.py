"""DL-PR05a: taxonomia de erros OpLab e leitura de ``Retry-After`` sem retry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.derivatives.oplab.errors import (
    RATE_LIMIT_BLOCK_S,
    UNAVAILABLE_BLOCK_S,
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
    classify_status,
    parse_retry_after,
)

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
ROUTE = "/market/status"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthError),
        (402, SubscriptionError),
        (403, PermissionError_),
        (404, NotFoundError),
        (429, RateLimitedError),
        (503, UnavailableError),
        (500, UnavailableError),
        (502, UnavailableError),
        (504, UnavailableError),
    ],
)
def test_status_maps_to_its_own_class(status: int, expected: type[OplabError]) -> None:
    error = classify_status(status, retry_after=None, now=NOW, route=ROUTE)
    assert type(error) is expected
    assert error.status == status
    assert error.route == ROUTE


@pytest.mark.parametrize("status", [400, 405, 418, 422])
def test_unmapped_client_status_is_the_base_error_without_window(status: int) -> None:
    error = classify_status(status, retry_after="120", now=NOW, route=ROUTE)
    assert type(error) is OplabError
    assert error.next_eligible_at is None
    assert error.retry_after_s is None


def test_all_errors_share_one_root_and_do_not_shadow_the_builtin() -> None:
    for error_type in (ForbiddenRouteError, ForbiddenHostError, AuthError, SubscriptionError,
                       PermissionError_, NotFoundError, RateLimitedError, UnavailableError,
                       BudgetExceededError, TransportError, NetworkForbiddenError):
        assert issubclass(error_type, OplabError)
    assert not issubclass(PermissionError_, PermissionError)
    assert not issubclass(AuthError, RateLimitedError)


@pytest.mark.parametrize("status", [429, 503])
def test_retry_after_seconds_sets_next_eligible_at(status: int) -> None:
    error = classify_status(status, retry_after="120", now=NOW, route=ROUTE)
    assert error.retry_after_s == 120.0
    assert error.next_eligible_at == NOW + timedelta(seconds=120)


def test_retry_after_http_date_is_parsed() -> None:
    error = classify_status(429, retry_after="Wed, 18 Nov 2026 15:02:00 GMT", now=NOW,
                            route=ROUTE)
    assert error.retry_after_s == 120.0
    assert error.next_eligible_at == NOW + timedelta(minutes=2)


def test_missing_retry_after_uses_the_published_blocks() -> None:
    limited = classify_status(429, retry_after=None, now=NOW, route=ROUTE)
    unavailable = classify_status(503, retry_after=None, now=NOW, route=ROUTE)
    assert RATE_LIMIT_BLOCK_S == 300.0
    assert UNAVAILABLE_BLOCK_S == 1.0
    assert limited.next_eligible_at == NOW + timedelta(seconds=300)
    assert unavailable.next_eligible_at == NOW + timedelta(seconds=1)


@pytest.mark.parametrize("header", ["soon", "", "-5", "1.5", "12 seconds", "NaN"])
def test_unreadable_retry_after_falls_back_to_the_published_block(header: str) -> None:
    error = classify_status(429, retry_after=header, now=NOW, route=ROUTE)
    assert error.next_eligible_at == NOW + timedelta(seconds=300)


def test_parse_retry_after_edge_cases() -> None:
    assert parse_retry_after(None, now=NOW) is None
    assert parse_retry_after(" 7 ", now=NOW) == 7.0
    assert parse_retry_after("0", now=NOW) == 0.0
    past = "Wed, 18 Nov 2026 14:00:00 GMT"
    assert parse_retry_after(past, now=NOW) == 0.0
    naive = "Wed, 18 Nov 2026 15:00:30"
    assert parse_retry_after(naive, now=NOW) == 30.0


@pytest.mark.parametrize("status", [401, 402, 403, 404])
def test_non_throttling_errors_carry_no_window_even_with_header(status: int) -> None:
    error = classify_status(status, retry_after="60", now=NOW, route=ROUTE)
    assert error.next_eligible_at is None


def test_classify_returns_without_raising_and_message_is_safe() -> None:
    error = classify_status(401, retry_after=None, now=NOW, route=ROUTE)
    assert isinstance(error, AuthError)
    assert error.message_safe == str(error)
    for forbidden in ("Access-Token", "test-token-not-real", "{", "http"):
        assert forbidden not in error.message_safe


def test_error_keeps_only_safe_metadata() -> None:
    error = OplabError("mensagem segura", status=418, route=ROUTE)
    assert vars(error) == {
        "message_safe": "mensagem segura", "status": 418, "route": ROUTE,
        "retry_after_s": None, "next_eligible_at": None,
    }
