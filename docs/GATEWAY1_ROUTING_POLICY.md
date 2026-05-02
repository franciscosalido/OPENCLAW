# Gateway-1 Routing Policy

Gateway-0 is closed. Gateway-1 begins with local-first routing policy
primitives only: no remote providers, no remote calls, no API keys, and no
runtime routing changes.

## Decision Shape

`backend/gateway/routing_policy.py` defines safe metadata records:

- `RouterDecision`: whether a request remains `local`, is a
  `remote_candidate`, or is `blocked`.
- `TokenEconomyRecord`: estimated local/remote token accounting for the
  decision.
- `RemoteEscalationPolicy`: explicit policy inputs. Its default is
  `remote_enabled=False` and `allowed_remote_providers=()`.
- `RoutingDecisionLogger`: append-only local JSONL audit writer.
- `TokenBudgetAccumulator`: in-memory session token estimate accumulator.

The module is deterministic and offline. It does not read environment secrets,
does not call a provider, and does not serialize prompt, query, answer, chunks,
vectors, payloads or credentials.

## Current Policy

The Gateway-1 prelude keeps the system local-first:

- Small and low-risk tasks route local.
- Sensitive context never becomes remote-allowed.
- High-value or expensive tasks may be recorded as remote candidates only if a
  future policy explicitly enables remote routing and lists a provider.
- With remote disabled, high-value or expensive tasks are blocked with
  `remote_disabled`.
- Budget overflow is blocked with `budget_exceeded`.
- Config-driven `blocked_task_types` default to `trade_execution` and
  `brokerage_login`.
- Empty `allowed_task_types` means all non-blocked task types are allowed.

Remote candidate records are planning metadata, not permission to call remote
APIs.

## Token Economy

Token economy values are estimates only. They are not billing records.

`TokenEconomyRecord` may record:

- estimated local tokens;
- estimated remote tokens;
- estimated remote tokens avoided.

The default `cost_estimate_mode` is `estimated_not_billed`.

Prompt token estimation uses a local heuristic:

```text
ceil(len(text.strip()) / chars_per_token), bounded by min_tokens
```

No tokenizer dependency is introduced.

`TokenBudgetAccumulator` is session-scoped and in-memory only. It does not
persist data and does not use a global singleton.

## Local JSONL Audit

`RoutingDecisionLogger` writes one safe JSON object per line to a local file.
With daily rotation enabled, the path is:

```text
logs/routing_decisions_YYYY-MM-DD.jsonl
```

These files are local audit artifacts and must not be committed. They never
include prompt, query, answer, chunks, vectors, payloads, API keys,
Authorization headers or secrets.

## Configuration

`config/rag_config.yaml` contains:

```yaml
gateway:
  routing:
    remote_enabled: false
    default_route: local
    log_decisions: true
    decision_log_path: logs/routing_decisions
    decision_log_rotate_daily: true
    allow_remote_candidates: true
    allowed_remote_providers: []
    per_request_token_limit: 0
    blocked_task_types:
      - trade_execution
      - brokerage_login
    allowed_task_types: []
    token_estimation:
      chars_per_token: 4
      min_tokens: 1
```

This config is declarative and policy-only. It does not change chat/RAG runtime
execution.

## Deferred

- Local fallback on timeout is not implemented in GW-14.
- Health-aware runtime routing is not implemented in GW-14.
- Sanitization must be implemented before any remote provider can be enabled.
- Remote provider enablement requires a future Accepted ADR.

## Future Requirements

Before any future remote call:

- an explicit ADR must be accepted;
- sanitization must exist and be tested;
- remote provider configuration must be reviewed;
- budget policy must be enforced;
- secrets must remain outside committed files.

Gateway-1 starts with records, config and tests so future routing work has a
safe contract to build on.
