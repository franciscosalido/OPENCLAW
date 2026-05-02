# Gateway-1 Token Economy

Gateway-1 token economy is local, heuristic and non-billing.

## Scope

GW-14 records estimated token usage for routing decisions. It does not call
remote providers, does not read API keys, and does not use a tokenizer
dependency.

## Estimation

Prompt token estimation uses:

```text
ceil(len(text.strip()) / chars_per_token)
```

The result is bounded by `min_tokens`.

Defaults:

- `chars_per_token: 4`
- `min_tokens: 1`

These estimates are useful for routing policy and local audit records. They are
not billing records and should not be treated as exact provider usage.

## Session Accumulation

`TokenBudgetAccumulator` is in-memory only. It can add:

- `RouterDecision`
- `TokenEconomyRecord`

It tracks:

- estimated prompt tokens;
- estimated completion tokens;
- estimated remote tokens;
- estimated remote tokens avoided.

No global singleton is created and no persistence is performed.

## Safety

Token economy records must not include prompt text, query text, answers,
chunks, vectors, payloads, portfolio data, API keys, Authorization headers or
secrets.
