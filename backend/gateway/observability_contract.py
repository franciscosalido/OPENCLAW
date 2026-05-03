"""Canonical safe observability signal contracts for Agent-0.

This module is intentionally side-effect free. It defines allowlists used by
tests and documentation to verify that observability records never serialize
prompt text, chunks, vectors, payloads or secrets.
"""

from __future__ import annotations

from collections.abc import Mapping


ROUTER_DECISION_KEYS = frozenset(
    {
        "decision_id",
        "route",
        "reason",
        "policy_outcome",
        "task_type",
        "estimated_prompt_tokens",
        "estimated_completion_tokens",
        "estimated_remote_tokens",
        "estimated_remote_tokens_avoided",
        "timestamp_utc",
        # Existing routing metadata kept for backward-compatible serializers.
        "risk_level",
        "token_budget_class",
        "remote_allowed",
        "remote_candidate_provider",
        "requires_sanitization",
    }
)

TOKEN_ECONOMY_RECORD_KEYS = frozenset(
    {
        "decision_id",
        "estimated_prompt_tokens",
        "estimated_completion_tokens",
        "estimated_remote_tokens_avoided",
        "local_budget_consumed",
        "remote_budget_consumed",
        "timestamp_utc",
        # Existing token economy metadata kept for backward-compatible
        # serializers and local audit records.
        "provider_used",
        "route",
        "local_tokens_estimated",
        "remote_tokens_estimated",
        "remote_tokens_avoided_estimated",
        "cost_estimate_mode",
    }
)

RAG_RUN_TRACE_KEYS = frozenset(
    {
        "decision_id",
        "query_id",
        "timestamp_utc",
        "collection_name",
        "embedding_backend",
        "embedding_model",
        "embedding_alias",
        "embedding_dimensions",
        "gateway_alias",
        "used_rag",
        "fallback_occurred",
        "chunk_count",
        "retrieval_latency_ms",
        "generation_latency_ms",
        "total_latency_ms",
        # Existing safe trace fields.
        "guard_result",
        "strict_mode",
        "prompt_latency_ms",
        "context_chunk_count",
        # Gateway-2 per-segment latency baseline fields.
        "routing_ms",
        "embedding_ms",
        "retrieval_ms",
        "context_pack_ms",
        # Gateway-2 context budget experiment fields.
        "context_budget_enabled",
        "context_budget_applied",
        "context_chunks_retrieved",
        "context_chunks_used",
        "context_chunks_dropped",
        "context_budget_max_chunks",
        "context_estimated_tokens_used",
        # Gateway-2 local_rag generation budget fields.
        "answer_length_chars",
        "answer_token_estimate",
        "generation_budget_enabled",
        "generation_budget_applied",
        "generation_budget_max_tokens",
        "conciseness_instruction_applied",
        "prompt_build_ms",
        "generation_ms",
        "total_ms",
        "run_context",
        "ollama_metrics_available",
        "ollama_total_duration_ms",
        "ollama_load_duration_ms",
        "ollama_prompt_eval_count",
        "ollama_prompt_eval_duration_ms",
        "ollama_eval_count",
        "ollama_eval_duration_ms",
    }
)

FALLBACK_EVENT_KEYS = frozenset(
    {
        "event",
        "event_kind",
        "decision_id",
        "fallback_reason",
        "original_alias",
        "fallback_alias",
        "fallback_succeeded",
        "latency_ms",
        "status",
        "timestamp_utc",
    }
)

DECISION_LOG_KEYS = frozenset(
    {
        "decision_id",
        "route",
        "reason",
        "policy_outcome",
        "estimated_remote_tokens_avoided",
        "timestamp_utc",
        # Existing RoutingDecisionLogger compatibility fields.
        "risk_level",
        "token_budget_class",
        "remote_allowed",
        "remote_candidate_provider",
        "requires_sanitization",
        "task_type",
        "estimated_prompt_tokens",
        "estimated_completion_tokens",
        "estimated_remote_tokens",
    }
)

AGENT_RUN_RESULT_KEYS = frozenset(
    {
        "answer",
        "route",
        "alias",
        "used_rag",
        "latency_ms",
        "decision_id",
        "estimated_remote_tokens_avoided",
        "error_category",
        "fallback_applied",
        "fallback_from_alias",
        "fallback_to_alias",
        "fallback_reason",
        "fallback_chain",
        "block_reason",
    }
)

GOLDEN_RESULT_KEYS = frozenset(
    {
        "question_id",
        "domain",
        "mode",
        "route",
        "alias",
        "used_rag",
        "latency_ms",
        "decision_id",
        "estimated_remote_tokens_avoided",
        "answer_length_chars",
        "error_category",
        "fallback_applied",
        "fallback_reason",
        "quality_score",
        "skipped",
        "skipped_reason",
    }
)

GOLDEN_SUMMARY_KEYS = frozenset(
    {
        "run_id",
        "timestamp_utc",
        "total_questions",
        "passed",
        "failed",
        "skipped",
        "fallback_count",
        "mean_latency_ms_by_alias",
        "p95_latency_ms_by_alias",
        "total_estimated_remote_tokens_avoided",
        "quality_score_present",
        "model_under_test_aliases",
    }
)

PROHIBITED_SIGNAL_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "user_prompt",
        "query",
        "question",
        "raw_user_input",
        "input_text",
        "chunks",
        "chunk",
        "chunk_text",
        "retrieved_context",
        "context_text",
        "vectors",
        "vector",
        "embeddings",
        "embedding",
        "payload",
        "qdrant_payload",
        "api_key",
        "authorization",
        "headers",
        "secret",
        "password",
        "raw_response",
        "raw_exception",
        "exception_message",
        "traceback",
        "model_weights_path",
        "weights_path",
    }
)

SAFE_ROUTER_REASON_VALUES = frozenset(
    {
        "budget_exceeded",
        "remote_disabled",
        "sensitive_context",
        "unsupported_task",
        "policy_denied",
        "unknown",
        # Existing deterministic local policy outcomes.
        "local_first_default",
        "remote_candidate_policy_match",
    }
)

SAFE_FALLBACK_REASON_VALUES = frozenset(
    {
        "qdrant_unavailable",
        "rag_unavailable",
        "think_timeout",
        "alias_unavailable",
        "budget_exceeded",
        "unsupported_task",
        "fallback_alias_failed",
        "unknown_local_failure",
    }
)


def assert_signal_allowlisted(
    signal: Mapping[str, object],
    *,
    allowlist: frozenset[str],
    signal_name: str,
) -> None:
    """Raise ``AssertionError`` if a signal violates its allowlist."""
    keys = frozenset(signal)
    extra_keys = keys - allowlist
    if extra_keys:
        raise AssertionError(
            f"{signal_name} contains non-allowlisted keys: {sorted(extra_keys)}"
        )
    prohibited = {key for key in keys if key.lower() in PROHIBITED_SIGNAL_KEYS}
    if prohibited:
        raise AssertionError(
            f"{signal_name} contains prohibited keys: {sorted(prohibited)}"
        )


def token_economy_canonical_signal(
    record: Mapping[str, object],
) -> dict[str, object]:
    """Project existing token economy metadata into canonical GW-19 fields."""
    signal: dict[str, object] = {}
    if "decision_id" in record:
        signal["decision_id"] = record["decision_id"]
    if "timestamp_utc" in record:
        signal["timestamp_utc"] = record["timestamp_utc"]
    if "remote_tokens_avoided_estimated" in record:
        signal["estimated_remote_tokens_avoided"] = record[
            "remote_tokens_avoided_estimated"
        ]
    if "local_tokens_estimated" in record:
        signal["local_budget_consumed"] = record["local_tokens_estimated"]
    if "remote_tokens_estimated" in record:
        signal["remote_budget_consumed"] = record["remote_tokens_estimated"]
    return signal
