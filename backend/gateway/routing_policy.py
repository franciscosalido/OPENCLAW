"""Local-first Gateway-1 routing policy primitives.

This module is intentionally offline and side-effect free. It never reads API
keys, never calls remote providers, and never serializes prompt or response
content. Gateway-1 can use these records to discuss routing decisions before
any future remote provider is enabled by ADR.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


DEFAULT_RAG_CONFIG_PATH = Path("config/rag_config.yaml")
DEFAULT_BLOCKED_TASK_TYPES = ("trade_execution", "brokerage_login")


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


class FallbackReason(str, Enum):
    """Safe local fallback reasons for Agent-0 degradation."""

    QDRANT_UNAVAILABLE = "qdrant_unavailable"
    RAG_UNAVAILABLE = "rag_unavailable"
    THINK_TIMEOUT = "think_timeout"
    ALIAS_UNAVAILABLE = "alias_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSUPPORTED_TASK = "unsupported_task"
    FALLBACK_ALIAS_FAILED = "fallback_alias_failed"
    UNKNOWN_LOCAL_FAILURE = "unknown_local_failure"


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
    blocked_task_types: tuple[str, ...] = DEFAULT_BLOCKED_TASK_TYPES
    allowed_task_types: tuple[str, ...] = ()

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
        for task_type in self.blocked_task_types:
            _validate_non_empty(task_type, "blocked_task_types")
        for task_type in self.allowed_task_types:
            _validate_non_empty(task_type, "allowed_task_types")


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
    task_type: str | None = None
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
        if self.task_type is not None:
            _validate_non_empty(self.task_type, "task_type")
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
            "task_type": self.task_type,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "estimated_completion_tokens": self.estimated_completion_tokens,
            "estimated_remote_tokens": self.estimated_remote_tokens,
            "estimated_remote_tokens_avoided": self.estimated_remote_tokens_avoided,
        }
        for key, value in optional_values.items():
            if value is not None:
                data[key] = value
        return data

    def decision_fingerprint(self) -> str:
        """Return a stable hash from safe policy-relevant fields only."""
        payload: dict[str, object | None] = {
            "route": self.route.value,
            "reason": self.reason,
            "risk_level": self.risk_level.value,
            "token_budget_class": self.token_budget_class.value,
            "remote_allowed": self.remote_allowed,
            "remote_candidate_provider": self.remote_candidate_provider,
            "requires_sanitization": self.requires_sanitization,
            "task_type": self.task_type,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "estimated_completion_tokens": self.estimated_completion_tokens,
            "estimated_remote_tokens": self.estimated_remote_tokens,
            "estimated_remote_tokens_avoided": self.estimated_remote_tokens_avoided,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


class TokenBudgetAccumulator:
    """In-memory session token estimate accumulator."""

    def __init__(self) -> None:
        self._totals = {
            "estimated_prompt_tokens": 0,
            "estimated_completion_tokens": 0,
            "estimated_remote_tokens": 0,
            "estimated_remote_tokens_avoided": 0,
        }

    def add(self, decision: RouterDecision | TokenEconomyRecord) -> None:
        """Add safe token estimate fields from one decision or record."""
        if isinstance(decision, RouterDecision):
            values = {
                "estimated_prompt_tokens": decision.estimated_prompt_tokens,
                "estimated_completion_tokens": decision.estimated_completion_tokens,
                "estimated_remote_tokens": decision.estimated_remote_tokens,
                "estimated_remote_tokens_avoided": (
                    decision.estimated_remote_tokens_avoided
                ),
            }
        else:
            values = {
                "estimated_prompt_tokens": None,
                "estimated_completion_tokens": None,
                "estimated_remote_tokens": decision.remote_tokens_estimated,
                "estimated_remote_tokens_avoided": (
                    decision.remote_tokens_avoided_estimated
                ),
            }
        for key, value in values.items():
            if value is None:
                continue
            _validate_non_negative(value, key)
            self._totals[key] += value

    def total(self) -> dict[str, int]:
        """Return accumulated session totals."""
        return dict(self._totals)

    def reset(self) -> None:
        """Reset accumulated session totals."""
        for key in self._totals:
            self._totals[key] = 0


class RoutingDecisionLogger:
    """Append safe routing decisions to a local JSONL audit file."""

    def __init__(
        self,
        base_path: Path | str,
        *,
        rotate_daily: bool = True,
        enabled: bool = True,
    ) -> None:
        self.base_path = Path(base_path)
        self.rotate_daily = rotate_daily
        self.enabled = enabled

    def append(self, decision: RouterDecision | TokenEconomyRecord) -> Path | None:
        """Append one safe JSON object and return the file path written."""
        if not self.enabled:
            return None
        path = self._log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = decision.to_log_dict()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")
        return path

    def _log_path(self) -> Path:
        stem_path = self.base_path.with_suffix("")
        if self.rotate_daily:
            date = datetime.now(UTC).date().isoformat()
            return stem_path.with_name(f"{stem_path.name}_{date}").with_suffix(
                ".jsonl"
            )
        return stem_path.with_suffix(".jsonl")


def load_routing_policy(
    config_path: Path | str = DEFAULT_RAG_CONFIG_PATH,
) -> RemoteEscalationPolicy:
    """Load a safe local-first routing policy from ``config/rag_config.yaml``."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if raw is None:
        return RemoteEscalationPolicy()
    if not isinstance(raw, Mapping):
        raise ValueError("routing config root must be a mapping")
    gateway = raw.get("gateway", {})
    if gateway is None:
        gateway = {}
    if not isinstance(gateway, Mapping):
        raise ValueError("gateway config must be a mapping")
    routing = gateway.get("routing", {})
    if routing is None:
        routing = {}
    if not isinstance(routing, Mapping):
        raise ValueError("gateway.routing config must be a mapping")

    remote_enabled = _read_bool(routing, "remote_enabled", default=False)
    monthly_budget_usd = _read_optional_float(routing, "monthly_budget_usd")
    per_request_token_limit = _read_optional_int(
        routing,
        "per_request_token_limit",
    )
    allowed_remote_providers = _read_string_tuple(
        routing,
        "allowed_remote_providers",
        default=(),
    )
    blocked_task_types = _read_string_tuple(
        routing,
        "blocked_task_types",
        default=DEFAULT_BLOCKED_TASK_TYPES,
    )
    allowed_task_types = _read_string_tuple(
        routing,
        "allowed_task_types",
        default=(),
    )

    return RemoteEscalationPolicy(
        remote_enabled=remote_enabled,
        monthly_budget_usd=monthly_budget_usd,
        per_request_token_limit=per_request_token_limit,
        allowed_remote_providers=allowed_remote_providers,
        blocked_task_types=blocked_task_types,
        allowed_task_types=allowed_task_types,
    )


def estimate_prompt_tokens(
    text: str,
    *,
    chars_per_token: int = 4,
    min_tokens: int = 1,
) -> int:
    """Estimate prompt tokens using a conservative local heuristic.

    This is an estimate for local policy decisions, not a billing record.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if chars_per_token <= 0:
        raise ValueError("chars_per_token must be greater than zero")
    if min_tokens < 0:
        raise ValueError("min_tokens cannot be negative")
    stripped = text.strip()
    estimated = ceil(len(stripped) / chars_per_token) if stripped else 0
    return max(estimated, min_tokens)


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

    # Decision priority ladder — intentional ordering:
    #
    # 1. budget_exceeded  → BLOCKED
    #    Checked first because it is a hard operational gate that applies
    #    regardless of content sensitivity. A budget-exhausted task would
    #    otherwise fall through to the sensitive_context branch and produce
    #    LOCAL instead of BLOCKED, silently allowing unbounded local usage.
    #    BLOCKED is strictly more restrictive than LOCAL, so placing this
    #    first is the conservative choice.
    #
    # 2. sensitive_context → LOCAL
    #    Sensitive content is forced local, not blocked. LOCAL is the safe
    #    outcome here: the task is allowed to run, but only on-device.
    #    Checked after budget so that a budget-exceeded + sensitive task is
    #    rejected outright rather than silently routed locally.
    #
    # 3. unsupported_task  → BLOCKED
    #    Hard prohibition on trade_execution and brokerage_login.
    #    Placed after content checks because task-type is a structural block
    #    that does not interact with budget or sensitivity.
    #
    # 4. high_value / expensive → REMOTE_CANDIDATE or BLOCKED
    #    Only reaches remote if policy explicitly enables it and at least one
    #    provider is configured. Default policy disables this path entirely.
    #
    # 5. default           → LOCAL (local_first_default)
    if _budget_exceeded(total_tokens, policy.per_request_token_limit):
        return _decision(
            route=RouteDecisionKind.BLOCKED,
            reason=RouteBlockReason.BUDGET_EXCEEDED.value,
            risk_level=risk_level,
            token_budget_class=TokenBudgetClass.BLOCKED,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=contains_sensitive_context,
            task_type=clean_task_type,
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
            task_type=clean_task_type,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_remote_tokens=total_tokens,
            estimated_remote_tokens_avoided=total_tokens,
        )

    if _is_unsupported_task(clean_task_type, policy):
        return _decision(
            route=RouteDecisionKind.BLOCKED,
            reason=RouteBlockReason.UNSUPPORTED_TASK.value,
            risk_level=TaskRiskLevel.HIGH,
            token_budget_class=TokenBudgetClass.BLOCKED,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=False,
            task_type=clean_task_type,
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
                task_type=clean_task_type,
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
            task_type=clean_task_type,
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
        task_type=clean_task_type,
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
    task_type: str,
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
        task_type=task_type,
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


def _is_unsupported_task(task_type: str, policy: RemoteEscalationPolicy) -> bool:
    clean_task_type = task_type.strip().lower()
    blocked = {item.strip().lower() for item in policy.blocked_task_types}
    allowed = {item.strip().lower() for item in policy.allowed_task_types}
    if clean_task_type in blocked:
        return True
    return bool(allowed) and clean_task_type not in allowed


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


def _read_bool(
    mapping: Mapping[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"gateway.routing.{key} must be a boolean")
    return value


def _read_optional_int(mapping: Mapping[str, Any], key: str) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"gateway.routing.{key} must be an integer")
    return value


def _read_optional_float(mapping: Mapping[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"gateway.routing.{key} must be a number")
    return float(value)


def _read_string_tuple(
    mapping: Mapping[str, Any],
    key: str,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = mapping.get(key, list(default))
    if not isinstance(value, list):
        raise ValueError(f"gateway.routing.{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"gateway.routing.{key} must contain only strings")
        result.append(_validate_non_empty(item, key))
    return tuple(result)
