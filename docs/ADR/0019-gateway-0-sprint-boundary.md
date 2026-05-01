# ADR-0019: Gateway-0 Sprint Boundary

## Status

Accepted

## Context

Gateway-0 delivered the local-first model gateway foundation for
Quimera/OpenClaw. The sprint established LiteLLM as the local model gateway,
kept Qdrant as the vector store, and added safe provenance and local
observability without enabling remote providers or broad service architecture.

## Decision

Gateway-0 is accepted as a local-only operational baseline.

Delivered components:

- LiteLLM local gateway at `http://127.0.0.1:4000/v1`.
- Ollama/Qwen local chat aliases: `local_chat`, `local_think`, `local_rag`,
  and `local_json`.
- `quimera_embed` as canonical embedding alias through OpenAI-compatible
  `/v1/embeddings`.
- `local_embed` as compatibility embedding alias.
- Qdrant as the RAG vector store.
- Controlled embedding migration with `direct_ollama` rollback.
- Synthetic RAG E2E smoke with temporary collections only.
- Collection metadata guard for embedding provenance drift.
- `RagRunTrace` as safe per-query provenance.
- `RagObservabilityEvent` as local lifecycle event metadata.
- Healthcheck/readiness scripts as operational gates.

## Boundaries

Gateway-0 is local only.

No remote provider is enabled. Future remote providers require an explicit ADR.

FastAPI, MCP and quant tools are out of Gateway-0 scope.

Real portfolio data, real documents, private files and Level 0 data are out of
scope for Gateway-0 tests and smoke commands.

`openclaw_knowledge` ingestion, mutation, reindexing or cleanup requires an
explicit future sprint.

## Architecture Rules

- Application callers use semantic aliases, not vendor model names.
- LiteLLM owns model-provider compatibility for gateway calls.
- Qdrant owns vector storage; LiteLLM is not a vector database.
- Vector metadata must preserve real embedding provider/model/dimensions.
- Vectors from different embedding models, dimensions, providers or backends
  must not be mixed silently in the same collection.
- Readiness checks must be local-only and must not print secrets.
- Live smoke must remain opt-in and must not become mandatory CI.

## Observability Rules

`RagRunTrace` is the final safe per-query provenance record.

`RagObservabilityEvent` is a local lifecycle event for internal stages.

Neither may include query text, prompt text, answer text, chunk text, document
text, vectors, Qdrant payloads, portfolio data, API keys, Authorization
headers, tokens, passwords or secrets.

## Future Work Requiring ADR Or Sprint

- Remote model providers.
- OpenTelemetry, distributed tracing, profiling or remote observability.
- FastAPI service layer.
- MCP/tooling integration.
- Quant tool management.
- Production `openclaw_knowledge` ingestion or reindexing.
- Any automatic collection healing or destructive Qdrant operation.

## Consequences

Gateway-0 closes with an operable local baseline. Future work can build on a
documented gateway, embedding, provenance and readiness foundation without
changing the local-only safety boundary by accident.
