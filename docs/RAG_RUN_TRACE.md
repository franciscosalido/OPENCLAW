# RAG Run Trace

GW-10 adds a safe per-query provenance record for local RAG executions.

`RagRunTrace` is not OpenTelemetry, not full observability, and not telemetry.
It is a compact runtime record of which safe RAG metadata was used for a query.

## Safe Fields

`RagRunTrace` records:

- `query_id`
- `timestamp_utc`
- `collection_name`
- `embedding_backend`
- `embedding_model`
- `embedding_alias`
- `embedding_dimensions`
- `retrieval_latency_ms`
- `generation_latency_ms`
- `chunk_count`
- optional `gateway_alias`
- optional safe `guard_result` summary
- optional `strict_mode`
- optional `total_latency_ms`
- optional `prompt_latency_ms`
- optional `context_chunk_count`

G2-01 extends the trace with optional per-segment latency fields for
measurement-only RAG baselining:

- `routing_ms`
- `embedding_ms`
- `retrieval_ms`
- `context_pack_ms`
- `prompt_build_ms`
- `generation_ms`
- `total_ms`
- `run_context`

See `docs/RAG_LATENCY_BASELINE.md` for exact segment boundaries.

G2-02 extends the trace with optional whole-chunk context budget fields:

- `context_budget_enabled`
- `context_budget_applied`
- `context_chunks_retrieved`
- `context_chunks_used`
- `context_chunks_dropped`
- `context_budget_max_chunks`
- `context_estimated_tokens_used`

These fields are safe scalar counts only. They do not include chunk text,
prompt text, answers, vectors, Qdrant payloads or secrets.

G2-03 extends the trace with optional `local_rag` generation budget fields:

- `answer_length_chars`
- `answer_token_estimate`
- `generation_budget_enabled`
- `generation_budget_applied`
- `generation_budget_max_tokens`
- `conciseness_instruction_applied`

These fields are safe scalar metadata only. They make output length and budget
application observable without storing answer text.

## Forbidden Content

The trace must never contain:

- query text
- prompt text
- answer text
- chunk text
- vectors
- Qdrant payloads
- portfolio data
- private documents
- API keys
- Authorization headers
- secrets

## Runtime Behavior

When `rag.tracing.enabled` is true, `LocalRagPipeline` emits:

```python
logger.bind(trace=trace.to_log_dict()).log(log_level, "rag_run_trace")
```

The trace is emitted after retrieval, prompt construction, and generation have
completed. If tracing is disabled, no trace event is emitted.

## Config

```yaml
rag:
  tracing:
    enabled: true
    log_level: "INFO"
```

Allowed log levels are `DEBUG`, `INFO`, and `WARNING`.

## Dimension Safety

`build_rag_run_trace()` validates the trace embedding dimensions against the
active expected dimensions. A mismatch raises
`EmbeddingDimensionMismatchError`, matching the GW-09 collection guard
semantics.

## Future Work

- GW-11 adds structured observability lifecycle events separately in
  `RagObservabilityEvent`.
- Future Gateway-2 work may add token-economy recalibration against the final
  capped prompt, still without logging prompt or answer content.
