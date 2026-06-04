# RAG-01B-PR-06 — OpenTelemetry Base Layer

Status: Draft implementation

## Objective

Create the base OpenTelemetry layer for Quimera/OpenClaw without instrumenting
the live RAG runtime end-to-end.

This PR adds idempotent tracing setup, safe attribute constants, async-only
decorators, context propagation helpers, base metrics, safe span events, a
LiteLLM OTel callback guard and an `otel-doctor` command.

## Decisions

- OpenTelemetry is optional at runtime and disabled quietly when
  `OTEL_SDK_DISABLED=true`.
- When no OTLP HTTP endpoint is configured, spans use the local console
  exporter.
- OTLP HTTP is the only remote exporter configured in this PR.
- AsyncPG instrumentation is best-effort and idempotent.
- LiteLLM remains a host process; this PR does not add a LiteLLM Docker service.
- LiteLLM OTel callback must be present with message logging disabled.

## Attribute Contract

Quimera uses a hybrid semantic model:

- OpenTelemetry GenAI semantic conventions for model, agent, tool, retrieval and
  evaluation metadata.
- MCP-compatible attributes where future tool spans need them.
- Quimera-specific attributes for local RAG/cache/fusion/latency metadata.

Prompt text, query text, answers, responses, chunks, documents, vectors,
embeddings, raw payloads, authorization data, API keys, tokens, passwords,
secrets and full DSNs are forbidden in attributes and span events.

`gen_ai.response.model` is explicitly allowed because it is model metadata, not
response content.

## Runtime Contract

`backend/observability/tracer.py` exposes:

- `setup_tracing()`
- `setup_observability(instrument_asyncpg=True)`
- `get_tracer(name)`
- `get_meter(name)`
- `shutdown_tracing()`
- `force_flush_tracing(timeout_millis=30000)`
- `instrument_asyncpg_once()`
- `is_otel_disabled()`

Batch span processor settings are controlled by:

- `QUIMERA_OTEL_MAX_QUEUE_SIZE`
- `QUIMERA_OTEL_MAX_EXPORT_BATCH_SIZE`
- `QUIMERA_OTEL_SCHEDULE_DELAY_MILLIS`
- `QUIMERA_OTEL_EXPORT_TIMEOUT_MILLIS`

`QUIMERA_OTEL_MAX_EXPORT_BATCH_SIZE` must be less than or equal to
`QUIMERA_OTEL_MAX_QUEUE_SIZE`.

## LiteLLM

`infra/litellm/litellm_config.yaml` includes:

- `litellm_settings.callbacks: ["otel"]`
- `litellm_settings.turn_off_message_logging: true`
- `callback_settings.otel.message_logging: false`

The doctor checks these settings without starting LiteLLM and without calling
Ollama or any model endpoint.

## Out Of Scope

- Full RAG pipeline instrumentation.
- Dashboards, collectors, Grafana, Tempo, Jaeger or Prometheus.
- MCP server, API, gRPC or runtime gateway changes.
- PostgreSQL/Timescale schema changes.
- Qdrant collection changes.
- Capturing raw prompt/response/chunk/vector content.

## Handoff To PR-07

PR-07 should wire these decorators into selected RAG and gateway seams, define
sampling policy for local development, and decide whether a collector/profile is
worth adding as an optional operator path.

## RC-01 Residual Risk Cleanup

RC-01 addressed reviewer residual risks without widening PR-06 into runtime RAG
instrumentation:

- `traced_pg` now emits current OpenTelemetry database semantic convention
  metadata for PostgreSQL:
  - `db.system.name=postgresql`
  - `db.operation.name`
  - `db.collection.name`
  Existing `quimera.pg_table`, `quimera.pg_operation` and `latency.pg_ms`
  remain for the Quimera contract.
- Metric instrument names are public constants:
  - `GENAI_OPERATION_DURATION_METRIC_NAME`
  - `RETRIEVAL_OPERATION_DURATION_METRIC_NAME`
- OTel integration smoke tests are marked with `pytest.mark.integration`.
- `traced_mcp_tool` validates `tool_name`/`method_name`, stores the tool name
  only as `gen_ai.tool.name`, and uses the low-cardinality MCP method in the
  span name.
