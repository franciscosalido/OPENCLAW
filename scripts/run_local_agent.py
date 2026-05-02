#!/usr/bin/env python
"""Agent-0 local runner MVP.

This CLI is local-only. It never calls remote providers and never includes the
raw question, prompt, chunks, vectors, payloads or secrets in metadata output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    GatewayChatClient,
)
from backend.gateway.routing_policy import (
    FallbackReason,
    RemoteEscalationPolicy,
    RouteBlockReason,
    RouteDecisionKind,
    RouterDecision,
    decide_route,
    estimate_prompt_tokens,
    load_routing_policy,
)
from scripts.rag_ask_local import ask_local


LOCAL_CHAT_ALIAS = DEFAULT_LLM_MODEL
LOCAL_RAG_ALIAS = DEFAULT_LLM_RAG_MODEL
LOCAL_JSON_ALIAS = DEFAULT_LLM_JSON_MODEL
SAFE_ERROR_CATEGORIES = {
    "blocked",
    "chat_unavailable",
    "json_unavailable",
    "rag_unavailable",
    "fallback_alias_failed",
    "invalid_arguments",
}

__all__ = [
    "AgentRunResult",
    "main",
    "main_async",
    "parse_args",
    "render_result",
    "run_agent",
]


class ChatCallable(Protocol):
    """Callable used by tests to replace the live chat path."""

    def __call__(
        self,
        question: str,
        *,
        alias: str,
        max_tokens: int | None,
        temperature: float | None,
        response_format: Mapping[str, object] | None,
    ) -> Awaitable[str]:
        """Return an answer from a local alias."""
        ...


class RagCallable(Protocol):
    """Callable used by tests to replace the live RAG path."""

    def __call__(
        self,
        question: str,
        *,
        max_tokens: int | None,
        temperature: float | None,
    ) -> Awaitable[str]:
        """Return an answer from the local RAG pipeline."""
        ...


@dataclass(frozen=True)
class AgentRunResult:
    """Safe Agent-0 runner result."""

    answer: str
    route: str
    alias: str
    used_rag: bool
    latency_ms: float
    decision_id: str
    estimated_remote_tokens_avoided: int
    error_category: str | None = None
    fallback_applied: bool | None = None
    fallback_from_alias: str | None = None
    fallback_to_alias: str | None = None
    fallback_reason: FallbackReason | None = None
    fallback_chain: tuple[FallbackReason, ...] | None = None
    block_reason: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        """Return the safe public output schema."""
        data: dict[str, object] = {
            "answer": self.answer,
            "route": self.route,
            "alias": self.alias,
            "used_rag": self.used_rag,
            "latency_ms": self.latency_ms,
            "decision_id": self.decision_id,
            "estimated_remote_tokens_avoided": self.estimated_remote_tokens_avoided,
        }
        if self.error_category is not None:
            data["error_category"] = self.error_category
        if self.fallback_applied is not None:
            data["fallback_applied"] = self.fallback_applied
        if self.fallback_from_alias is not None:
            data["fallback_from_alias"] = self.fallback_from_alias
        if self.fallback_to_alias is not None:
            data["fallback_to_alias"] = self.fallback_to_alias
        if self.fallback_reason is not None:
            data["fallback_reason"] = self.fallback_reason.value
        if self.fallback_chain:
            data["fallback_chain"] = [reason.value for reason in self.fallback_chain]
        if self.block_reason is not None:
            data["block_reason"] = self.block_reason
        return data


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse Agent-0 CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run one local-only Agent-0 question.",
    )
    parser.add_argument("question", help="Question to answer locally.")
    parser.add_argument("--rag", action="store_true", help="Use local RAG path.")
    parser.add_argument("--json", action="store_true", help="Use local_json alias.")
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="Include safe metadata in text mode.",
    )
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Return routing decision and token estimates without model calls.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include exception class only on safe failures.",
    )
    args = parser.parse_args(argv)
    if args.rag and args.json:
        parser.error("--rag and --json cannot be used together")
    if args.max_tokens is not None and args.max_tokens <= 0:
        parser.error("--max-tokens must be greater than zero")
    if args.temperature is not None and not 0.0 <= args.temperature <= 2.0:
        parser.error("--temperature must be between 0.0 and 2.0")
    return args


async def run_agent(
    *,
    question: str,
    use_rag: bool = False,
    use_json: bool = False,
    max_tokens: int | None = None,
    temperature: float | None = None,
    dry_run: bool = False,
    debug: bool = False,
    chat_call: ChatCallable | None = None,
    rag_call: RagCallable | None = None,
    policy_loader: Callable[[], RemoteEscalationPolicy] | None = None,
) -> AgentRunResult:
    """Run one local Agent-0 request and return a safe result."""
    if use_rag and use_json:
        raise ValueError("--rag and --json cannot be used together")
    alias = _select_alias(use_rag=use_rag, use_json=use_json)
    estimated_prompt_tokens = _estimate_prompt_token_count(question)
    estimated_completion_tokens = max_tokens or 512
    policy = policy_loader() if policy_loader is not None else _safe_policy()
    decision = decide_route(
        task_type=_task_type(use_rag=use_rag, use_json=use_json),
        estimated_prompt_tokens=estimated_prompt_tokens,
        estimated_completion_tokens=estimated_completion_tokens,
        contains_sensitive_context=False,
        high_value_task=False,
        policy=policy,
    )
    avoided = decision.estimated_remote_tokens_avoided
    safe_avoided = int(avoided or 0)

    if decision.route is RouteDecisionKind.BLOCKED:
        return AgentRunResult(
            answer="Request blocked by local routing policy.",
            route=decision.route.value,
            alias=alias,
            used_rag=use_rag,
            latency_ms=0.0,
            decision_id=decision.decision_id,
            estimated_remote_tokens_avoided=safe_avoided,
            error_category="blocked",
            fallback_applied=False,
            block_reason=_block_reason(decision),
        )

    if dry_run:
        return AgentRunResult(
            answer="Dry run: no model call executed.",
            route=decision.route.value,
            alias=alias,
            used_rag=use_rag,
            latency_ms=0.0,
            decision_id=decision.decision_id,
            estimated_remote_tokens_avoided=safe_avoided,
        )

    start = time.perf_counter()
    try:
        if use_rag:
            active_rag_call = _call_rag if rag_call is None else rag_call
            try:
                answer = await active_rag_call(
                    question,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as rag_exc:
                active_chat_call = _call_chat_alias if chat_call is None else chat_call
                fallback_reason = _rag_fallback_reason(rag_exc)
                try:
                    answer = await active_chat_call(
                        question,
                        alias=LOCAL_CHAT_ALIAS,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=None,
                    )
                except Exception as chat_exc:
                    latency_ms = _elapsed_ms(start)
                    _emit_fallback_event(
                        decision_id=decision.decision_id,
                        fallback_reason=fallback_reason,
                        original_alias=LOCAL_RAG_ALIAS,
                        fallback_alias=LOCAL_CHAT_ALIAS,
                        fallback_succeeded=False,
                        latency_ms=latency_ms,
                    )
                    error_category = "fallback_alias_failed"
                    if debug:
                        error_category = f"{error_category}:{chat_exc.__class__.__name__}"
                    return AgentRunResult(
                        answer="Local Agent-0 execution failed.",
                        route=decision.route.value,
                        alias=LOCAL_CHAT_ALIAS,
                        used_rag=False,
                        latency_ms=latency_ms,
                        decision_id=decision.decision_id,
                        estimated_remote_tokens_avoided=safe_avoided,
                        error_category=error_category,
                        fallback_applied=True,
                        fallback_from_alias=LOCAL_RAG_ALIAS,
                        fallback_to_alias=LOCAL_CHAT_ALIAS,
                        fallback_reason=fallback_reason,
                        fallback_chain=(fallback_reason,),
                    )

                latency_ms = _elapsed_ms(start)
                _emit_fallback_event(
                    decision_id=decision.decision_id,
                    fallback_reason=fallback_reason,
                    original_alias=LOCAL_RAG_ALIAS,
                    fallback_alias=LOCAL_CHAT_ALIAS,
                    fallback_succeeded=True,
                    latency_ms=latency_ms,
                )
                return AgentRunResult(
                    answer=answer,
                    route=decision.route.value,
                    alias=LOCAL_CHAT_ALIAS,
                    used_rag=False,
                    latency_ms=latency_ms,
                    decision_id=decision.decision_id,
                    estimated_remote_tokens_avoided=safe_avoided,
                    fallback_applied=True,
                    fallback_from_alias=LOCAL_RAG_ALIAS,
                    fallback_to_alias=LOCAL_CHAT_ALIAS,
                    fallback_reason=fallback_reason,
                    fallback_chain=(fallback_reason,),
                )
        else:
            active_chat_call = _call_chat_alias if chat_call is None else chat_call
            answer = await active_chat_call(
                question,
                alias=alias,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"} if use_json else None,
            )
    except Exception as exc:
        if use_rag:
            error_category = "rag_unavailable"
        elif use_json:
            error_category = "json_unavailable"
        else:
            error_category = "chat_unavailable"
        if debug:
            error_category = f"{error_category}:{exc.__class__.__name__}"
        return AgentRunResult(
            answer="Local Agent-0 execution failed.",
            route=decision.route.value,
            alias=alias,
            used_rag=use_rag,
            latency_ms=_elapsed_ms(start),
            decision_id=decision.decision_id,
            estimated_remote_tokens_avoided=safe_avoided,
            error_category=error_category,
        )

    return AgentRunResult(
        answer=answer,
        route=decision.route.value,
        alias=alias,
        used_rag=use_rag,
        latency_ms=_elapsed_ms(start),
        decision_id=decision.decision_id,
        estimated_remote_tokens_avoided=safe_avoided,
    )


async def _call_chat_alias(
    question: str,
    *,
    alias: str,
    max_tokens: int | None,
    temperature: float | None,
    response_format: Mapping[str, object] | None,
) -> str:
    async with GatewayChatClient() as client:
        return await client.chat_completion(
            [{"role": "user", "content": question}],
            model=alias,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )


async def _call_rag(
    question: str,
    *,
    max_tokens: int | None,
    temperature: float | None,
) -> str:
    del max_tokens, temperature
    result = await ask_local(question=question, model=LOCAL_RAG_ALIAS)
    return result.answer


def render_result(result: AgentRunResult, *, output: str, show_metadata: bool) -> str:
    """Render a safe CLI result."""
    if output == "json":
        return json.dumps(result.to_json_dict(), ensure_ascii=False, sort_keys=True)
    if not show_metadata:
        return result.answer
    metadata = result.to_json_dict()
    metadata.pop("answer", None)
    return result.answer + "\n\nmetadata=" + json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )


async def main_async(argv: Sequence[str] | None = None) -> int:
    """Async CLI entrypoint."""
    args = parse_args(argv)
    result = await run_agent(
        question=args.question,
        use_rag=args.rag,
        use_json=args.json,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        dry_run=args.dry_run,
        debug=args.debug,
    )
    sys.stdout.write(
        render_result(result, output=args.output, show_metadata=args.show_metadata)
        + "\n"
    )
    return 1 if result.error_category else 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return asyncio.run(main_async(argv))


def _safe_policy() -> RemoteEscalationPolicy:
    """Load routing policy from config with safe fallback."""
    try:
        return load_routing_policy()
    except Exception:
        return RemoteEscalationPolicy(remote_enabled=False)


def _estimate_prompt_token_count(question: str) -> int:
    """Estimate prompt token count using the local heuristic."""
    return estimate_prompt_tokens(question)


def _select_alias(*, use_rag: bool, use_json: bool) -> str:
    if use_rag:
        return LOCAL_RAG_ALIAS
    if use_json:
        return LOCAL_JSON_ALIAS
    return LOCAL_CHAT_ALIAS


def _task_type(*, use_rag: bool, use_json: bool) -> str:
    if use_rag:
        return "agent0_rag"
    if use_json:
        return "agent0_json"
    return "agent0_chat"


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _block_reason(decision: RouterDecision) -> str:
    """Return a safe block reason from routing policy metadata."""
    if decision.reason == RouteBlockReason.BUDGET_EXCEEDED.value:
        return RouteBlockReason.BUDGET_EXCEEDED.value
    if decision.reason == RouteBlockReason.UNSUPPORTED_TASK.value:
        return RouteBlockReason.UNSUPPORTED_TASK.value
    return decision.reason


def _rag_fallback_reason(exc: Exception) -> FallbackReason:
    """Classify a RAG failure without exposing exception details."""
    class_name = exc.__class__.__name__.lower()
    module_name = exc.__class__.__module__.lower()
    if "qdrant" in class_name or "qdrant" in module_name:
        return FallbackReason.QDRANT_UNAVAILABLE
    return FallbackReason.RAG_UNAVAILABLE


def _emit_fallback_event(
    *,
    decision_id: str,
    fallback_reason: FallbackReason,
    original_alias: str,
    fallback_alias: str,
    fallback_succeeded: bool,
    latency_ms: float,
) -> None:
    """Emit a safe local fallback event with allowlisted metadata only."""
    event: dict[str, object] = {
        "event": "agent_fallback",
        "decision_id": decision_id,
        "fallback_reason": fallback_reason.value,
        "original_alias": original_alias,
        "fallback_alias": fallback_alias,
        "fallback_succeeded": fallback_succeeded,
        "latency_ms": latency_ms,
        "status": "success" if fallback_succeeded else "failure",
    }
    logger.bind(event=event).info("agent_fallback")


if __name__ == "__main__":
    raise SystemExit(main())
