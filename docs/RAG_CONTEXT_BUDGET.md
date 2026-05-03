# RAG Context Budget Cap

G2-02 adds an optional local-only context budget cap for `local_rag`.

This is a reversible performance experiment. It does not change retrieval,
`top_k`, Qdrant search, embeddings, model aliases, timeouts, prompt template, or
generation settings.

## Configuration

The cap is controlled by `config/rag_config.yaml`:

```yaml
rag:
  context_budget:
    enabled: false
    max_context_chunks: 3
    mode: "whole_chunks"
    apply_to_aliases:
      - "local_rag"
```

Rollback is a single config change:

```yaml
rag:
  context_budget:
    enabled: false
```

`enabled: false` preserves the pre-G2-02 behavior.

## Strategy

G2-02 uses `max_context_chunks` as the primary budget control.

The cap is applied inside `ContextPacker` after the existing deterministic
deduplication, token-limit selection, and document-position ordering logic.
When enabled and the final packed context has more chunks than
`max_context_chunks`, the packer keeps the first whole chunks from the existing
packer ordering.

The cap never:

- cuts a chunk in the middle;
- strips `doc_id`, `chunk_index`, payload metadata, or citation ids;
- mutates Qdrant;
- changes retrieved vectors, embeddings, or stored documents;
- changes prompt templates or model aliases.

`max_context_chars` and token-based truncation are intentionally deferred. A
future G2 follow-up can evaluate token budgeting after this whole-chunk
experiment produces stable before/after measurements.

## Trace Fields

`RagRunTrace` records safe budget metadata when available:

- `context_budget_enabled`
- `context_budget_applied`
- `context_chunks_retrieved`
- `context_chunks_used`
- `context_chunks_dropped`
- `context_budget_max_chunks`
- `context_estimated_tokens_used`

These fields contain counts only. They never include prompt text, chunk text,
answers, vectors, payloads, API keys, headers, raw exceptions, or tracebacks.

## Token Economy Limitation

G2-02 does not change the Agent-0 runner output schema.

If a caller estimates token economy before prompt construction, that estimate may
not yet reflect the capped final RAG prompt. G2-02 records
`context_estimated_tokens_used` in `RagRunTrace` so the limitation is observable
without logging the prompt. Full recalibration of
`estimated_remote_tokens_avoided` against the final capped prompt is deferred to
a follow-up PR.

## Validation

Offline validation should prove:

- budget disabled returns the same chunks as before;
- budget enabled caps whole chunks only;
- citation metadata survives the cap;
- trace metadata reports retrieved/used/dropped chunk counts;
- Agent-0 result schema remains unchanged;
- no live Qdrant, Ollama, or LiteLLM services are required for unit tests.

Optional live validation can compare uncapped and capped `local_rag` runs with
the same synthetic question, checking:

- `context_chunks_retrieved`;
- `context_chunks_used`;
- `context_chunks_dropped`;
- `prompt_eval_duration_ms` if available;
- `generation_ms`;
- `total_ms`;
- citation presence.

Do not commit generated reports.
