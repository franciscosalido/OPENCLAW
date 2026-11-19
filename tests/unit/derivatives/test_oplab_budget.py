"""DL-PR05a: orcamento por credencial com relogio injetado — sem sleep, sem relogio real."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.derivatives.oplab.budget import (
    BudgetSnapshot,
    RequestBudget,
    credential_key,
)
from backend.derivatives.oplab.errors import BudgetExceededError
from config.derivatives_config_model import Budget

T0 = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
TOKEN = "test-token-not-real"


def _budget(**overrides: int) -> RequestBudget:
    return RequestBudget(Budget(**overrides), key=credential_key(TOKEN))


def test_default_limits_are_the_published_ones() -> None:
    cfg = Budget()
    assert (cfg.per_second, cfg.per_minute, cfg.max_retries) == (50, 100, 0)


def test_fifty_in_the_same_second_pass_and_the_next_is_refused() -> None:
    budget = _budget()
    for _ in range(50):
        budget.acquire(T0)
    with pytest.raises(BudgetExceededError) as refused:
        budget.acquire(T0 + timedelta(milliseconds=999))
    assert refused.value.next_eligible_at == T0 + timedelta(seconds=1)
    assert budget.snapshot(T0) == BudgetSnapshot(50, 50, None)
    budget.acquire(T0 + timedelta(seconds=1))


def test_hundred_in_a_minute_pass_and_the_next_is_refused() -> None:
    budget = _budget()
    for index in range(100):
        budget.acquire(T0 + timedelta(milliseconds=500 * index))
    late = T0 + timedelta(seconds=55)
    with pytest.raises(BudgetExceededError) as refused:
        budget.acquire(late)
    assert refused.value.next_eligible_at == T0 + timedelta(minutes=1)
    assert budget.snapshot(late).used_per_minute == 100
    budget.acquire(T0 + timedelta(minutes=1))
    assert budget.snapshot(T0 + timedelta(minutes=1)).used_per_minute == 100


def test_refused_attempt_does_not_consume_budget() -> None:
    budget = _budget(per_second=1, per_minute=5)
    budget.acquire(T0)
    for _ in range(10):
        with pytest.raises(BudgetExceededError):
            budget.acquire(T0)
    assert budget.snapshot(T0).used_per_minute == 1


def test_window_slides_instead_of_resetting() -> None:
    budget = _budget(per_second=2, per_minute=100)
    budget.acquire(T0)
    budget.acquire(T0 + timedelta(milliseconds=600))
    with pytest.raises(BudgetExceededError) as refused:
        budget.acquire(T0 + timedelta(milliseconds=900))
    assert refused.value.next_eligible_at == T0 + timedelta(seconds=1)
    budget.acquire(T0 + timedelta(milliseconds=1000))
    with pytest.raises(BudgetExceededError) as again:
        budget.acquire(T0 + timedelta(milliseconds=1100))
    assert again.value.next_eligible_at == T0 + timedelta(milliseconds=1600)


def test_block_until_refuses_until_the_instant_and_never_shortens() -> None:
    budget = _budget()
    until = T0 + timedelta(minutes=5)
    budget.block_until(until)
    budget.block_until(T0 + timedelta(seconds=10))
    with pytest.raises(BudgetExceededError) as refused:
        budget.acquire(until - timedelta(microseconds=1))
    assert refused.value.next_eligible_at == until
    assert budget.snapshot(T0).blocked_until == until
    budget.acquire(until)
    assert budget.snapshot(until).blocked_until is None


def test_clock_going_backwards_stays_conservative() -> None:
    budget = _budget(per_second=1, per_minute=100)
    budget.acquire(T0)
    with pytest.raises(BudgetExceededError):
        budget.acquire(T0 - timedelta(seconds=5))


def test_credential_key_is_a_digest_and_never_the_token() -> None:
    key = credential_key(TOKEN)
    assert len(key) == 64 and int(key, 16) >= 0
    assert TOKEN not in key and TOKEN[:8] not in key
    assert key == credential_key(TOKEN[:8] + "outro-sufixo")
    assert key != credential_key("outro-token-not-real")
    budget = _budget()
    assert TOKEN not in repr(vars(budget))
    assert budget.key == key


def test_budgets_of_different_credentials_are_independent() -> None:
    first = RequestBudget(Budget(per_second=1), key=credential_key("aaaaaaaa-1"))
    second = RequestBudget(Budget(per_second=1), key=credential_key("bbbbbbbb-2"))
    first.acquire(T0)
    second.acquire(T0)
    with pytest.raises(BudgetExceededError):
        first.acquire(T0)
