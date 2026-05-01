# ADR-0020: Controlled Remote Escalation Policy

**Status:** Proposed  
**Date:** 2026-05-01

## Context

Gateway-0 delivered a local-only model gateway with LiteLLM, Ollama/Qwen,
`quimera_embed`, Qdrant RAG, provenance tracing, lifecycle observability, and
operational readiness checks.

Gateway-1 may eventually need policy decisions about whether a request remains
local, is blocked, or becomes a candidate for remote escalation. Remote
providers are not enabled in GW-13.

## Decision

Introduce local-first routing decision primitives and token economy records.
These records are safe metadata only. They do not authorize remote calls.

The default remote escalation policy is:

- `remote_enabled: false`;
- no allowed remote providers;
- no remote API keys;
- no remote calls.

## Rules

- Sensitive context must never be remote-allowed by default.
- High-value or expensive tasks are blocked while remote routing is disabled.
- Token economy is estimated and not billed.
- Routing serialization uses an explicit allowlist.
- Prompt, query, answer, chunk, vector, payload and secret content are never
  serialized.
- Remote provider enablement requires a future Accepted ADR.

## Consequences

Gateway-1 can discuss routing choices and estimated token avoidance without
changing runtime model routing or adding providers.

Future work must add sanitization, budget enforcement, explicit provider
approval and security review before any remote calls are possible.

## Out of Scope

- Remote provider enablement.
- Remote API calls.
- API key configuration.
- LiteLLM remote provider aliases.
- FastAPI, MCP, quant tools, dashboards, OpenTelemetry, or distributed tracing.
- Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge` access.

## Revision Policy

This ADR must move from Proposed to Accepted before Gateway-1 enables any
remote escalation path. Any provider-specific routing requires its own
reviewable follow-up.
