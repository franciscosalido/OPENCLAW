# Gateway-1 Sprint Handoff

**Last updated:** 2026-05-02
**Current branch:** `feat/agent0-golden-question-harness`
**Issue:** [#61](https://github.com/franciscosalido/OPENCLAW/issues/61)

Gateway-0 is complete. Gateway-1 starts with routing policy primitives and
token economy records only.

## GW-13 Completed Work

Scope:

- Add `backend/gateway/routing_policy.py`.
- Add offline routing decision records.
- Add token economy estimate records.
- Add declarative `gateway.routing` config with remote disabled.
- Add deterministic unit tests.
- Add ADR-0020 as Proposed.

Out of scope:

- Remote provider enablement.
- Remote calls.
- API keys.
- Runtime model routing changes.
- LiteLLM remote provider config.
- Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge`.

## Safety Contract

- Remote providers remain disabled.
- `allowed_remote_providers` is empty by default.
- `remote_candidate` is only metadata for future review.
- Token economy is estimated, not billed.
- Serialized records must not include query, prompt, answer, chunks, vectors,
  payloads, API keys, Authorization headers or secrets.

## Planned Follow-ups

| Item | Scope |
|---|---|
| GW-14 | Config-driven routing audit and token economy calibration |
| GW-17 | Explicit local fail-safe degradation for Agent-0 runner |
| GW-18 | Golden question benchmark harness |

## GW-15 Current Work

Scope:

- Add `scripts/run_local_agent.py`.
- Add one-question Agent-0 local CLI.
- Route before execution using `decide_route(...)`.
- Default to `local_chat`.
- Use `local_json` only with `--json`.
- Use existing local RAG path only with `--rag`.
- Add safe JSON/text output.
- Add optional smoke script guarded by `RUN_AGENT0_LOCAL_SMOKE=1`.
- Add offline unit tests with mocks.

Out of scope:

- Remote providers and remote calls.
- Multi-agent orchestration.
- FastAPI, MCP, daemon/background workers.
- Qdrant mutation, reindexing, ingestion or production collection changes.
- Progressive fallback on timeout.
- Golden questions harness.

Safety:

- No prompt/query/chunk/vector/payload/secret fields in output metadata.
- Dry-run performs routing and token estimates without model calls.
- RAG unavailable returns `error_category=rag_unavailable`; no silent fallback in
  GW-15.

## GW-16 Current Work

Scope:

- Harden `scripts/run_local_agent.py` contracts with offline tests.
- Freeze alias matrix for `local_chat`, `local_json`, and `local_rag`.
- Freeze output schema invariants across success, dry-run, blocked and failure
  states.
- Validate degraded-state behavior for chat, JSON and RAG.
- Assert no silent fallback between aliases.
- Validate parse/render/token-estimate boundaries.

Out of scope:

- Progressive fallback.
- Retry/fallback on timeout.
- Golden questions harness.
- Remote providers or calls.
- Qdrant mutation, reindexing or ingestion.

Safety:

- Runner output still excludes prompt/query/chunks/vectors/payloads/secrets.
- Live services are not required for GW-16 tests.

## GW-17 Current Work

Scope:

- Add typed fallback reason vocabulary.
- Add safe optional fallback metadata to Agent-0 runner output.
- Fallback once from `local_rag` to `local_chat` when local RAG/Qdrant
  infrastructure is unavailable.
- Keep policy blocks as hard stops with no model call and no fallback.
- Add a no-double-fallback guard when the fallback alias also fails.
- Emit a sanitized local `agent_fallback` loguru event.
- Add offline tests for fallback, policy blocks, schema stability and exit
  codes.

Out of scope:

- Remote providers or remote calls.
- FastAPI, MCP or multi-agent orchestration.
- Qdrant mutation, reindexing, ingestion or `openclaw_knowledge` access.
- Public `local_think` runner path. `local_think` timeout fallback remains
  deferred until a think path exists.

Safety:

- Fallback reason codes are enum-derived.
- Fallback metadata excludes prompt/query/chunks/vectors/payloads/secrets.
- Successful fallback exits `0`; policy block and unrecoverable local failure
  exit non-zero.

## GW-18 Current Work

Scope:

- Add `tests/golden/questions.yaml` with fixed synthetic financial-domain
  questions.
- Add `scripts/run_golden_harness.py` with opt-in dry-run and optional live
  execution.
- Emit safe JSONL and summary JSON reports without answer text.
- Add `scripts/compare_golden_runs.py` for summary-to-summary regression checks.
- Add offline unit tests for registry, report schema, guard behavior and
  comparison logic.

Out of scope:

- Remote providers or remote calls.
- LLM-as-judge.
- Dashboards, OpenTelemetry, Prometheus or Grafana.
- Qdrant mutation, reindexing or `openclaw_knowledge` access.
- Live baseline publication. First committed live baseline requires a future
  explicit baseline-update decision.

Safety:

- Golden questions are synthetic-only.
- Reports exclude prompt/question/chunks/vectors/payloads/secrets and do not
  include answer text by default.
- `tests/golden/reports/` is ignored by Git.
