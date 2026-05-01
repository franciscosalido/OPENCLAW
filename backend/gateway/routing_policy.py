"""Local-first Gateway-1 routing policy primitives.

This module is intentionally offline and side-effect free. It never reads API
keys, never calls remote providers, and never serializes prompt or response
content. Gateway-1 can use these records to discuss routing decisions before
any future remote provider is enabled by ADR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class RouteDecisionKind(str, Enum):
    """Allowed high-level routing decisions."""

    LOCAL = "local"
    REMOTE_CANDIDATE = "remote_candidate"
    BLOCKED = "blocked"


class RouteBlockReason(str, Enum):
    """Safe routing block reasons."""

    REMOTE_DISABLED = "remote_disabled"
    SENSITIVE_CONTEXT = "sensitive_context"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSUPPORTED_TASK = "unsupported_task"
    POLICY_DENIED = "policy_denied"
    UNKNOWN = "unknown"


class TaskRiskLevel(str, Enum):
    """Coarse task risk levels used by routing policy."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TokenBudgetClass(str, Enum):
    """Estimated token budget class for policy decisions."""

    TINY = "tiny"
    NORMAL = "normal"
    EXPENSIVE = "expensive"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RemoteEscalationPolicy:
    """Local-first remote escalation policy.

    ``remote_enabled`` defaults to ``False`` and must stay false until a future
    ADR explicitly authorizes remote provider activation.
    """

    remote_enabled: bool = False
    monthly_budget_usd: float | None = None
    per_request_token_limit: int | None = None
    allowed_remote_providers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.monthly_budget_usd is not None and self.monthly_budget_usd < 0:
            raise ValueError("monthly_budget_usd cannot be negative")
        if (
            self.per_request_token_limit is not None
            and self.per_request_token_limit < 0
        ):
            raise ValueError("per_request_token_limit cannot be negative")
        for provider in self.allowed_remote_providers:
            _validate_non_empty(provider, "allowed_remote_providers")


@dataclass(frozen=True)
class RouterDecision:
    """Safe metadata-only record of a gateway routing decision."""

    decision_id: str
    timestamp_utc: str
    route: RouteDecisionKind
    reason: str
    risk_level: TaskRiskLevel
    token_budget_class: TokenBudgetClass
    remote_allowed: bool
    remote_candidate_provider: str | None
    requires_sanitization: bool
    estimated_prompt_tokens: int | None = None
    estimated_completion_tokens: int | None = None
    estimated_remote_tokens: int | None = None
    estimated_remote_tokens_avoided: int | None = None

    def __post_init__(self) -> None:
        _validate_non_empty(self.decision_id, "decision_id")
        _validate_non_empty(self.timestamp_utc, "timestamp_utc")
        _validate_non_empty(self.reason, "reason")
        if self.remote_candidate_provider is not None:
            _validate_non_empty(
                self.remote_candidate_provider,
                "remote_candidate_provider",
            )
        _validate_optional_non_negative(
            self.estimated_prompt_tokens,
            "estimated_prompt_tokens",
        )
        _validate_optional_non_negative(
            self.estimated_completion_tokens,
            "estimated_completion_tokens",
        )
        _validate_optional_non_negative(
            self.estimated_remote_tokens,
            "estimated_remote_tokens",
        )
        _validate_optional_non_negative(
            self.estimated_remote_tokens_avoided,
            "estimated_remote_tokens_avoided",
        )

    def to_log_dict(self) -> dict[str, object]:
        """Return safe allowlisted metadata for structured logs."""
        data: dict[str, object] = {
            "decision_id": self.decision_id,
            "timestamp_utc": self.timestamp_utc,
            "route": self.route.value,
            "reason": self.reason,
            "risk_level": self.risk_level.value,
            "token_budget_class": self.token_budget_class.value,
            "remote_allowed": self.remote_allowed,
            "requires_sanitization": self.requires_sanitization,
        }
        optional_values: dict[str, object | None] = {
            "remote_candidate_provider": self.remote_candidate_provider,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "estimated_completion_tokens": self.estimated_completion_tokens,
            "estimated_remote_tokens": self.estimated_remote_tokens,
            "estimated_remote_tokens_avoided": self.estimated_remote_tokens_avoided,
        }
        for key, value in optional_values.items():
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class TokenEconomyRecord:
    """Safe token economy estimate tied to one routing decision."""

    decision_id: str
    provider_used: str
    route: str
    local_tokens_estimated: int | None
    remote_tokens_estimated: int | None
    remote_tokens_avoided_estimated: int | None
    cost_estimate_mode: str
    timestamp_utc: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.decision_id, "decision_id")
        _validate_non_empty(self.provider_used, "provider_used")
        _validate_non_empty(self.route, "route")
        _validate_non_empty(self.cost_estimate_mode, "cost_estimate_mode")
        _validate_non_empty(self.timestamp_utc, "timestamp_utc")
        _validate_optional_non_negative(
            self.local_tokens_estimated,
            "local_tokens_estimated",
        )
        _validate_optional_non_negative(
            self.remote_tokens_estimated,
            "remote_tokens_estimated",
        )
        _validate_optional_non_negative(
            self.remote_tokens_avoided_estimated,
            "remote_tokens_avoided_estimated",
        )

    def to_log_dict(self) -> dict[str, object]:
        """Return safe allowlisted token economy metadata."""
        data: dict[str, object] = {
            "decision_id": self.decision_id,
            "provider_used": self.provider_used,
            "route": self.route,
            "cost_estimate_mode": self.cost_estimate_mode,
            "timestamp_utc": self.timestamp_utc,
        }
        optional_values: dict[str, int | None] = {
            "local_tokens_estimated": self.local_tokens_estimated,
            "remote_tokens_estimated": self.remote_tokens_estimated,
            "remote_tokens_avoided_estimated": self.remote_tokens_avoided_estimated,
        }
        for key, value in optional_values.items():
            if value is not None:
                data[key] = value
        return data


def decide_route(
    *,
    task_type: str,
    estimated_prompt_tokens: int,
    estimated_completion_tokens: int,
    contains_sensitive_context: bool,
    high_value_task: bool,
    policy: RemoteEscalationPolicy,
) -> RouterDecision:
    """Decide whether a task remains local, is blocked, or is a remote candidate.

    The function is deterministic and never performs I/O. A remote candidate is
    only returned when remote routing is explicitly enabled and at least one
    provider is explicitly allowed.
    """
    clean_task_type = _validate_non_empty(task_type, "task_type")
    _validate_non_negative(estimated_prompt_tokens, "estimated_prompt_tokens")
    _validate_non_negative(estimated_completion_tokens, "estimated_completion_tokens")
    total_tokens = estimated_prompt_tokens + estimated_completion_tokens
    budget_class = _token_budget_class(total_tokens)
    risk_level = _risk_level(
        contains_sensitive_context=contains_sensitive_context,
        high_value_task=high_value_task,
        budget_class=budget_class,
    )

    if _budget_exceeded(total_tokens, policy.per_request_token_limit):
        return _decision(
            route=RouteDecisionKind.BLOCKED,
            reason=RouteBlockReason.BUDGET_EXCEEDED.value,
            risk_level=risk_level,
            token_budget_class=TokenBudgetClass.BLOCKED,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=contains_sensitive_context,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_remote_tokens=total_tokens,
            estimated_remote_tokens_avoided=total_tokens,
        )

    if contains_sensitive_context:
        return _decision(
            route=RouteDecisionKind.LOCAL,
            reason=RouteBlockReason.SENSITIVE_CONTEXT.value,
            risk_level=TaskRiskLevel.HIGH,
            token_budget_class=budget_class,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=True,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_remote_tokens=total_tokens,
            estimated_remote_tokens_avoided=total_tokens,
        )

    if _is_unsupported_task(clean_task_type):
        return _decision(
            route=RouteDecisionKind.BLOCKED,
            reason=RouteBlockReason.UNSUPPORTED_TASK.value,
            risk_level=TaskRiskLevel.HIGH,
            token_budget_class=TokenBudgetClass.BLOCKED,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=False,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_remote_tokens=total_tokens,
            estimated_remote_tokens_avoided=total_tokens,
        )

    if high_value_task or budget_class is TokenBudgetClass.EXPENSIVE:
        provider = (
            policy.allowed_remote_providers[0]
            if policy.allowed_remote_providers
            else None
        )
        if policy.remote_enabled and provider is not None:
            return _decision(
                route=RouteDecisionKind.REMOTE_CANDIDATE,
                reason="remote_candidate_policy_match",
                risk_level=risk_level,
                token_budget_class=budget_class,
                remote_allowed=True,
                remote_candidate_provider=provider,
                requires_sanitization=True,
                estimated_prompt_tokens=estimated_prompt_tokens,
                estimated_completion_tokens=estimated_completion_tokens,
                estimated_remote_tokens=total_tokens,
                estimated_remote_tokens_avoided=None,
            )
        reason = (
            RouteBlockReason.REMOTE_DISABLED.value
            if not policy.remote_enabled
            else RouteBlockReason.POLICY_DENIED.value
        )
        return _decision(
            route=RouteDecisionKind.BLOCKED,
            reason=reason,
            risk_level=risk_level,
            token_budget_class=budget_class,
            remote_allowed=False,
            remote_candidate_provider=provider,
            requires_sanitization=True,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_remote_tokens=total_tokens,
            estimated_remote_tokens_avoided=total_tokens,
        )

    return _decision(
        route=RouteDecisionKind.LOCAL,
        reason="local_first_default",
        risk_level=risk_level,
        token_budget_class=budget_class,
        remote_allowed=False,
        remote_candidate_provider=None,
        requires_sanitization=False,
        estimated_prompt_tokens=estimated_prompt_tokens,
        estimated_completion_tokens=estimated_completion_tokens,
        estimated_remote_tokens=total_tokens,
        estimated_remote_tokens_avoided=total_tokens,
    )


def build_token_economy_record(
    decision: RouterDecision,
    *,
    provider_used: str = "local",
    cost_estimate_mode: str = "estimated_not_billed",
) -> TokenEconomyRecord:
    """Build a safe token economy estimate from a routing decision."""
    local_tokens = None
    if decision.route is RouteDecisionKind.LOCAL:
        local_tokens = _sum_optional(
            decision.estimated_prompt_tokens,
            decision.estimated_completion_tokens,
        )
    return TokenEconomyRecord(
        decision_id=decision.decision_id,
        provider_used=provider_used,
        route=decision.route.value,
        local_tokens_estimated=local_tokens,
        remote_tokens_estimated=decision.estimated_remote_tokens,
        remote_tokens_avoided_estimated=decision.estimated_remote_tokens_avoided,
        cost_estimate_mode=cost_estimate_mode,
        timestamp_utc=utc_now_iso(),
    )


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _decision(
    *,
    route: RouteDecisionKind,
    reason: str,
    risk_level: TaskRiskLevel,
    token_budget_class: TokenBudgetClass,
    remote_allowed: bool,
    remote_candidate_provider: str | None,
    requires_sanitization: bool,
    estimated_prompt_tokens: int,
    estimated_completion_tokens: int,
    estimated_remote_tokens: int | None,
    estimated_remote_tokens_avoided: int | None,
) -> RouterDecision:
    return RouterDecision(
        decision_id=uuid4().hex,
        timestamp_utc=utc_now_iso(),
        route=route,
        reason=reason,
        risk_level=risk_level,
        token_budget_class=token_budget_class,
        remote_allowed=remote_allowed,
        remote_candidate_provider=remote_candidate_provider,
        requires_sanitization=requires_sanitization,
        estimated_prompt_tokens=estimated_prompt_tokens,
        estimated_completion_tokens=estimated_completion_tokens,
        estimated_remote_tokens=estimated_remote_tokens,
        estimated_remote_tokens_avoided=estimated_remote_tokens_avoided,
    )


def _token_budget_class(total_tokens: int) -> TokenBudgetClass:
    if total_tokens <= 1_000:
        return TokenBudgetClass.TINY
    if total_tokens <= 8_000:
        return TokenBudgetClass.NORMAL
    return TokenBudgetClass.EXPENSIVE


def _risk_level(
    *,
    contains_sensitive_context: bool,
    high_value_task: bool,
    budget_class: TokenBudgetClass,
) -> TaskRiskLevel:
    if (
        contains_sensitive_context
        or high_value_task
        or budget_class is TokenBudgetClass.EXPENSIVE
    ):
        return TaskRiskLevel.HIGH
    if budget_class is TokenBudgetClass.NORMAL:
        return TaskRiskLevel.MEDIUM
    return TaskRiskLevel.LOW


def _budget_exceeded(total_tokens: int, limit: int | None) -> bool:
    return limit is not None and limit > 0 and total_tokens > limit


def _is_unsupported_task(task_type: str) -> bool:
    return task_type.strip().lower() in {"trade_execution", "brokerage_login"}


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return left + right


def _validate_non_empty(value: str, field_name: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def _validate_optional_non_negative(value: int | None, field_name: str) -> None:
    if value is not None:
        _validate_non_negative(value, field_name)
