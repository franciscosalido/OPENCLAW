# Gateway-1 Routing Policy Prelude

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

Remote candidate records are planning metadata, not permission to call remote
APIs.

## Token Economy

Token economy values are estimates only. They are not billing records.

`TokenEconomyRecord` may record:

- estimated local tokens;
- estimated remote tokens;
- estimated remote tokens avoided.

The default `cost_estimate_mode` is `estimated_not_billed`.

## Configuration

`config/rag_config.yaml` contains:

```yaml
gateway:
  routing:
    remote_enabled: false
    default_route: local
    log_decisions: true
    allow_remote_candidates: true
    allowed_remote_providers: []
    per_request_token_limit: 0
```

This config is declarative only in GW-13. It does not change model routing.

## Future Requirements

Before any future remote call:

- an explicit ADR must be accepted;
- sanitization must exist and be tested;
- remote provider configuration must be reviewed;
- budget policy must be enforced;
- secrets must remain outside committed files.

Gateway-1 starts with records and tests so future routing work has a safe
contract to build on.
