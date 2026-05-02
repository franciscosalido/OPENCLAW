# Gateway-1 Sprint Handoff

**Last updated:** 2026-05-01  
**Current branch:** `feat/gateway1-routing-policy-prelude`  
**Issue:** [#51](https://github.com/franciscosalido/OPENCLAW/issues/51)

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
| GW-14 | Sanitization policy before any remote escalation |
| GW-15 | Budget enforcement and approval flow |
| GW-16 | Provider-specific ADR if remote routing is ever proposed |

## GW-14 Current Work

Branch: `feat/gateway1-routing-audit-token-economy`
Issue: [#53](https://github.com/franciscosalido/OPENCLAW/issues/53)

Scope:

- Load `RemoteEscalationPolicy` from `config/rag_config.yaml`.
- Add local JSONL routing decision audit records.
- Add heuristic prompt token estimation.
- Add in-memory `TokenBudgetAccumulator`.
- Add config-driven blocked/allowed task type registry.
- Add stable `RouterDecision.decision_fingerprint()`.
- Add deterministic unit and integration tests.

Out of scope:

- Remote providers, API keys or remote calls.
- Runtime chat/RAG routing changes.
- Local fallback on timeout.
- Health-aware runtime routing.
- Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge`.

Safety:

- `remote_enabled` remains false.
- `allowed_remote_providers` remains empty.
- JSONL audit files are local and ignored by git.
- Token economy is estimated, not billed.
