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
- GW-12 will add memory/resource baseline work.
