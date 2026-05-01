# RAG Observability Events

GW-11 adds safe local lifecycle events for RAG operations.

These events are loguru structured logs only. They are not OpenTelemetry,
remote telemetry, distributed tracing, profiling, dashboards, Prometheus,
Grafana, soak testing, or memory/resource baselines.

## Purpose

`RagObservabilityEvent` records safe metadata for lifecycle stages:

- embedding calls
- retrieval
- generation
- collection guard warnings or errors when a caller already has that context

`RagRunTrace` and `RagObservabilityEvent` are different:

- `RagRunTrace` is the final per-query provenance record emitted after a RAG
  query completes.
- `RagObservabilityEvent` is a lifecycle event emitted around internal stages.

## Event Kinds

- `embedding_call_started`
- `embedding_call_finished`
- `embedding_call_failed`
- `retrieval_started`
- `retrieval_finished`
- `retrieval_failed`
- `generation_started`
- `generation_finished`
- `generation_failed`
- `collection_guard_warning`
- `collection_guard_error`

## Safe Fields

Events may include only safe scalar metadata:

- event kind
- timestamp
- backend
- alias
- model
- dimensions
- latency
- chunk count
- batch size
- status
- error category
- collection name
- query id
- gateway alias

## Forbidden Content

Events must never include:

- query text
- prompt text
- answer text
- chunk or document text
- vectors or embedding values
- Qdrant payloads
- portfolio data
- API keys
- Authorization headers
- tokens
- passwords
- secrets

Serialization uses an explicit allowlist and omits `None` values.

## Config

```yaml
rag:
  observability:
    enabled: true
    log_level: "INFO"
    embedding_events_enabled: true
    retrieval_events_enabled: true
    generation_events_enabled: true
    collection_guard_events_enabled: true
```

Allowed log levels are `DEBUG`, `INFO`, and `WARNING`.

## Current Integration

GW-11 emits embedding lifecycle events from:

- `GatewayEmbedClient` with `backend="gateway_litellm"`
- `OllamaEmbedder` with `backend="direct_ollama"`

It also emits retrieval and generation lifecycle events from
`LocalRagPipeline` when enabled.

Return values, retry/backoff/concurrency behavior, Qdrant collections, and
default embedding selection are unchanged.

## Future Work

GW-12 remains the place for memory/resource baseline work. OpenTelemetry or
remote observability is not part of GW-11.
