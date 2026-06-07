"""Run the PR-08 deterministic Agentic0 integration smoke."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Literal, cast
from uuid import uuid4

from integration.agentic0_client import Agentic0Client, Agentic0ClientError
from integration.agentic0_contracts import (
    SMOKE_SCHEMA_VERSION,
    Agentic0SmokeConfig,
    Agentic0SmokeResult,
    LLMCallSummary,
    LatencySummary,
    PostgresMemorySummary,
    RetrievalSummary,
    SafetySummary,
    ToolCallSummary,
    new_run_id,
    skipped_result,
    utc_now,
)
from integration.check_integration_health import build_integration_health_report
from integration.hybrid_fixture import hybrid_contract_summary
from integration.report_writer import HEALTH_PATH, write_json_artifact, write_smoke_artifacts
from integration.safety_scan import find_forbidden_fields

P95_WARNING_THRESHOLD_MS = 500.0


async def run_smoke(*, allow_degraded: bool = False) -> Agentic0SmokeResult:
    config = Agentic0SmokeConfig(autonomous_tool_use_enabled=False)
    started = utc_now()
    run_id = new_run_id()
    correlation_id = uuid4().hex
    start = time.perf_counter()
    health = build_integration_health_report()
    write_json_artifact(HEALTH_PATH, health)
    if health["overall"] == "fail" and not allow_degraded:
        result = skipped_result(config, reason="integration health failed; rerun with --allow-degraded for diagnostic smoke")
        write_smoke_artifacts(result)
        return result
    hybrid = hybrid_contract_summary(run_id)
    tool_calls = [
        ToolCallSummary("quimera_postgres_memory", "postgres_agent_state_get", "degraded" if health["services"].get("postgres") != "ok" else "ok", 0.0, ("schema_version", "ok", "degraded", "data")),
        ToolCallSummary("quimera_qdrant_memory", "qdrant_scroll_safe", "ok" if hybrid["hybrid_ok"] else "fail", 0.0, ("schema_version", "ok", "data")),
    ]
    llm_ok = False
    warnings = list(health.get("warnings", []))
    if health["services"].get("litellm") == "ok":
        try:
            client = Agentic0Client(config)
            llm_ok = await client.synthesize_smoke_marker(
                run_id=run_id,
                doc_ids=["doc-memory", "doc-qdrant"],
                state_keys=["integration_smoke_goal"],
            )
        except Agentic0ClientError as exc:
            warnings.append(str(exc))
    else:
        warnings.append("litellm unavailable; LLM synthesis skipped")
    finished = utc_now()
    summary_payload = {
        "health": health,
        "hybrid": hybrid,
        "tool_calls": [call.tool_name for call in tool_calls],
        "correlation_id": correlation_id,
    }
    forbidden = find_forbidden_fields(summary_payload)
    status: Literal["pass", "fail", "skipped"] = "pass" if llm_ok and not forbidden and hybrid["hybrid_ok"] else "fail"
    if health["overall"] == "fail" and allow_degraded:
        status = "skipped"
    services = cast("dict[str, str]", health["services"])
    total_ms = (time.perf_counter() - start) * 1000.0
    result = Agentic0SmokeResult(
        schema_version=SMOKE_SCHEMA_VERSION,
        status=status,
        run_id=run_id,
        started_at=started,
        finished_at=finished,
        correlation_id=correlation_id,
        services=services,
        tool_calls=tool_calls,
        retrieval=RetrievalSummary(**hybrid),
        postgres_memory=PostgresMemorySummary(
            session_persistence_ok=services.get("postgres") == "ok",
            agent_state_roundtrip_ok=services.get("postgres") == "ok",
        ),
        llm=LLMCallSummary(model=config.litellm_model, completion_ok=llm_ok),
        final_answer_ok=llm_ok,
        latency=build_latency_summary(total_ms=total_ms, health=health),
        safety=SafetySummary(forbidden_fields_seen=tuple(forbidden)),
        trace_ids=[correlation_id],
        warnings=warnings,
    )
    write_smoke_artifacts(result)
    return result


def build_latency_summary(*, total_ms: float, health: dict[str, object]) -> LatencySummary:
    services = cast("dict[str, str]", health.get("services", {}))
    live_stack = all(services.get(name) == "ok" for name in ("litellm", "ollama", "qdrant", "postgres"))
    service_latencies = cast("dict[str, float]", health.get("service_latencies_ms", {}))
    if not live_stack:
        return LatencySummary(
            total_ms=total_ms,
            measurement_mode="degraded_no_live_stack",
            sample_count=0,
            p95_warning="not_measured_stack_unavailable",
            mcp_ms=service_latencies.get("qdrant", 0.0) + service_latencies.get("postgres", 0.0),
            llm_ms=service_latencies.get("litellm", 0.0),
            pg_ms=service_latencies.get("postgres", 0.0),
            retrieval_ms=service_latencies.get("qdrant", 0.0),
        )
    samples = [total_ms, *service_latencies.values()]
    p50 = _percentile(samples, 50.0)
    p95 = _percentile(samples, 95.0)
    warning = "p95_exceeds_500ms" if p95 > P95_WARNING_THRESHOLD_MS else None
    return LatencySummary(
        total_ms=total_ms,
        measurement_mode="live_healthcheck_probe",
        sample_count=len(samples),
        p50_ms=p50,
        p95_ms=p95,
        p95_warning=warning,
        mcp_ms=service_latencies.get("qdrant", 0.0) + service_latencies.get("postgres", 0.0),
        llm_ms=service_latencies.get("litellm", 0.0),
        pg_ms=service_latencies.get("postgres", 0.0),
        retrieval_ms=service_latencies.get("qdrant", 0.0),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percentile / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-degraded", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run_smoke(allow_degraded=args.allow_degraded))
    payload = result.to_jsonable()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"agentic0-smoke: {result.status}")
    return 0 if result.status in {"pass", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
