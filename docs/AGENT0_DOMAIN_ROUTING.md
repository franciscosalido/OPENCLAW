# Agent-0 Domain Routing

## Purpose

A0-PR04 adds deterministic Agent-0 domain routing. It classifies a local query
with keyword/regex rules, combines the result with retrieval confidence and
system state, then chooses one local route:

- `local_rag`
- `local_think`
- `local_chat`

The router does not generate answers and does not call Qdrant, Ollama, LiteLLM
or remote providers.

## Deterministic Classifier

`backend/agent0/domain_classifier.py` is intentionally small and offline. It
does not import gateway clients, embedders, retrievers, vector stores or LLM
providers.

Supported domains:

- `internal`
- `macroeconomia`
- `renda_fixa`
- `valuation`
- `unknown`

Question ID prefixes are recognized:

- `iq-*` routes to `internal` and `openclaw_internal`.
- `fq-*` routes to the financial collection. Keyword/regex rules refine the
  financial domain when the query contains enough signal.

Keyword examples:

- `selic`, `inflacao`, `ipca` -> `macroeconomia`
- `duration`, `renda fixa`, `curva de juros` -> `renda_fixa`
- `ebitda`, `valuation`, `fluxo de caixa` -> `valuation`
- `gw-07`, `alias`, `timeout`, `decisions` -> `internal`

## Configuration

Thresholds and domain-rule metadata live in `config/rag_config.yaml`:

```yaml
agent0:
  domain_routing:
    retrieval_score_min: 0.75
    escalate_to_think_below: 0.45
    p95_routing_budget_ms: 100.0
    citation_weight: 0.2
    domain_rules:
      internal:
        corpus: internal
        collection_name: openclaw_internal
```

Validation enforces:

- `0 < escalate_to_think_below < retrieval_score_min <= 1.0`
- `p95_routing_budget_ms > 0`
- domain rules use only allowed corpora and collections
- regex patterns compile at load time
- `openclaw_knowledge` is not an allowed Agent-0 routing collection

## Route Decision Logic

`route(query, state, config, scorer, question_id=None)` performs:

1. Classify the domain.
2. If Qdrant is unavailable, return `local_chat` with reason
   `qdrant_unavailable`.
3. If the domain is unknown, return `local_chat` with reason
   `no_domain_match`.
4. Ask the injected `ConfidenceScorer` for retrieval confidence.
5. If confidence is at least `retrieval_score_min`, return `local_rag`.
6. If confidence is at least `escalate_to_think_below`, return `local_think`.
7. Otherwise return `local_chat`.

The router never calls Qdrant directly. Unit tests use `FakeConfidenceScorer`.

## RouteDecision Contract

`RouteDecision` is a frozen dataclass. Its `to_dict()` method is allowlisted and
contains only:

- `route`
- `corpus`
- `domain`
- `collection_name`
- `confidence_score`
- `threshold_used`
- `reason_code`
- `latency_ms`
- `fallback_reason` when present
- `routing_mode`

It never contains query text, retrieved text, prompts, answers, chunks, vectors,
embeddings, payloads, secrets, headers, tracebacks or absolute paths.

## Golden Question Gate

`validate_routing_against_golden_questions()` reuses A0-PR03 golden questions
with a fake high-confidence scorer. The gate checks that at least 5 of 6
questions route to the expected corpus and collection. The current deterministic
rules route all 6 of 6 to `local_rag` with the expected namespace.

## Dry-Run Latency Gate

`route_dry_run_p95()` runs 100 synthetic route decisions offline. It uses no
network, no Qdrant, no Ollama and no LLM generation. The p95 must stay below
`agent0.domain_routing.p95_routing_budget_ms`.

## Routing Report

`backend/agent0/routing_report.py` builds sanitized routing reports with:

- `run_id`
- `timestamp_utc`
- `total_decisions`
- `passed`
- `failed`
- `coverage`
- `p50_routing_ms`
- `p95_routing_ms`
- `route_counts`
- `reason_code_counts`
- `golden_accuracy`
- `per_decision`

Forbidden report keys include query, text, raw text, answer, prompt, chunks,
chunk text, vectors, embeddings, payloads, headers, API keys, authorization,
secrets, raw exceptions, tracebacks, absolute paths and usernames.

## Future Extension Points

Future PRs may wire a real confidence scorer that reads retrieval metadata from
an existing local retriever. That scorer must remain injectable and testable
with fakes, must not mutate Qdrant, and must preserve the same sanitized
decision/report contracts.
