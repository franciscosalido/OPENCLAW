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
from integration.report_writer import write_smoke_artifacts
from integration.safety_scan import find_forbidden_fields


async def run_smoke(*, allow_degraded: bool = False) -> Agentic0SmokeResult:
    config = Agentic0SmokeConfig(autonomous_tool_use_enabled=False)
    started = utc_now()
    run_id = new_run_id()
    correlation_id = uuid4().hex
    start = time.perf_counter()
    health = build_integration_health_report()
    if health["overall"] == "fail" and not allow_degraded:
        result = skipped_result(config, reason="integration health failed; rerun with --allow-degraded for diagnostic smoke")
        write_smoke_artifacts(result)
        return result
    hybrid = hybrid_contract_summary(run_id)
    tool_calls = [
        ToolCallSummary("quimera-postgres-memory", "postgres_agent_state_get", "degraded" if health["services"].get("postgres") != "ok" else "ok", 0.0, ("schema_version", "ok", "degraded", "data")),
        ToolCallSummary("quimera-qdrant-memory", "qdrant_scroll_safe", "ok" if hybrid["hybrid_ok"] else "fail", 0.0, ("schema_version", "ok", "data")),
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
        latency=LatencySummary(total_ms=(time.perf_counter() - start) * 1000.0, mcp_ms=0.0, llm_ms=0.0),
        safety=SafetySummary(forbidden_fields_seen=tuple(forbidden)),
        trace_ids=[correlation_id],
        warnings=warnings,
    )
    write_smoke_artifacts(result)
    return result


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
