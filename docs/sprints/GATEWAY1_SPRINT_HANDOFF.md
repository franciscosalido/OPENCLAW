# Gateway-1 Sprint Handoff

**Last updated:** 2026-05-01  
**Current branch:** `feat/agent0-runner-contract-hardening`
**Issue:** [#57](https://github.com/franciscosalido/OPENCLAW/issues/57)

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
| GW-17 | Progressive local fallback on timeout/alias failure |
| GW-18 | Golden questions harness |

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
