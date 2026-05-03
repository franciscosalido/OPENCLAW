# Agent-0 Observability Contract

GW-19 verifies Agent-0 observability signal completeness and sanitization.

This is not OpenTelemetry, not a dashboard, not remote telemetry and not a
runtime behavior change. It is an offline contract that tests existing local
signals.

## Signals

Agent-0 observability uses these safe metadata signals:

- `RouterDecision`: route selected, reason code, policy outcome and token
  estimates.
- `TokenEconomyRecord`: local estimate of remote tokens avoided and budget-like
  token totals.
- `RagRunTrace`: safe RAG provenance and segment latency metadata when RAG
  tracing is applicable.
- Decision logs: local JSONL audit records written by `RoutingDecisionLogger`.
- Fallback events: local `agent_fallback` loguru events when GW-17 fallback is
  applied.

## Allowlist Rule

Serializers are tested against explicit allowlists in
`backend/gateway/observability_contract.py`.

Tests assert that signal keys are a subset of the relevant allowlist. This is
intentional: new fields must be deliberately added to the allowlist before they
can appear in structured output.

## Prohibited Fields

The following categories must never appear as keys in Agent-0 observability
signals:

- prompt or system/user prompt
- query, question or raw user input
- chunks, retrieved context or context text
- vectors or embeddings
- payloads or Qdrant payloads
- API keys, Authorization headers, headers, tokens, passwords or secrets
- raw model responses
- raw exceptions, exception messages or tracebacks
- model weights paths

Tests use deterministic synthetic sentinels to verify that raw input and raw
exception text do not leak into outputs or fallback events.

## Reason Codes

Routing and fallback reasons must be deterministic safe codes.

Examples:

- `local_first_default`
- `budget_exceeded`
- `unsupported_task`
- `remote_disabled`
- `qdrant_unavailable`
- `rag_unavailable`
- `fallback_alias_failed`

Free-form exception messages are not valid reason codes.

## Correlation

Fallback events must include the same `decision_id` that appears in the
Agent-0 runner output. Decision logs and token-economy records are also keyed by
`decision_id`.

## Offline Coverage

GW-19 tests cover:

- RouterDecision serialization
- TokenEconomyRecord serialization and canonical projection
- RagRunTrace serialization
- fallback event sanitization and `decision_id` correlation
- local decision JSONL safety
- Agent-0 dry-run output safety
- estimated remote tokens avoided across success, dry-run, blocked, fallback
  success and fallback failure paths
- golden harness dry-run JSONL and summary safety

All tests are offline and deterministic. They do not require LiteLLM, Ollama,
Qdrant or network services.

## Gateway-1 Proof-of-Life

GW-20 adds an opt-in operator smoke that scans structured proof-of-life outputs
using the same prohibited-field discipline. It validates dry-run, local service
probes, live runner paths, forced degradation and policy block behavior, then
writes a sanitized summary JSON.

The proof-of-life smoke is not OpenTelemetry, not a dashboard, not remote
telemetry and not a profiling baseline. It is a local readiness gate for
Gateway-2.

## Deferred

`RagRunTrace` currently predates Agent-0 and does not carry Agent-0
`decision_id`, `used_rag` or `fallback_occurred` fields directly. The GW-19
allowlist reserves those fields for future integration, but does not force a
runtime schema change in this PR.

Future work may add a unified in-process signal collector, but that requires a
separate issue.

## Out Of Scope

- OpenTelemetry
- dashboards
- Prometheus/Grafana
- remote telemetry
- remote providers
- live baseline freeze
- LLM-as-judge
- Qdrant mutation or reindexing
