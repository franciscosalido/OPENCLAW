# RAG Embedding Migration

GW-08 introduces a controlled migration path for new RAG embedding generation.

## Current Decision

New controlled ingest/test paths may use:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text
```

The rollback path remains:

```text
RagEmbedder factory
  -> direct_ollama
  -> OllamaEmbedder
  -> Ollama /api/embed
```

`OllamaEmbedder` remains available. GW-08 does not remove direct Ollama
embedding support.

## Configuration

`config/rag_config.yaml` controls the active backend:

```yaml
rag:
  embedding:
    active_backend: "gateway_litellm"
    embedding_alias: "quimera_embed"
    embedding_backend: "gateway_litellm_current"
    legacy_embedding_backend: "direct_ollama"
```

For rollback during local development or controlled operations:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

The concrete model remains `nomic-embed-text` with 768 dimensions. Changing the
model, provider, or dimensions requires explicit reembedding/reindexing.

## Safety Rules

- Existing collections are not reindexed automatically.
- `openclaw_knowledge` is not touched by GW-08.
- Vectors from different embedding backends, models, providers, or dimensions
  must not be mixed silently in one collection.
- New controlled collections must persist embedding metadata:
  `embedding_provider`, `embedding_model`, `embedding_dimensions`,
  `embedding_version`, `embedding_contract`, `embedding_alias`, and
  `embedding_backend`.
- Real documents, real portfolio data, private files, and remote providers are
  out of scope for this migration.

## Migration Gates

Before using `gateway_litellm` for a controlled collection:

- Unit tests must pass.
- Gateway embedding parity must preserve retry/backoff/concurrency settings:
  `max_retries=3`, `backoff_seconds=1.0`, `max_concurrency=4`.
- Live parity smoke should show cosine similarity `>= 0.9999` against direct
  Ollama for synthetic input.
- Synthetic ingest/retrieval/generation smoke should pass using a temporary
  `gw08_embedding_migration_` collection.

## Live Validation Result

Local validation on 2026-04-30 passed with Qdrant, Ollama, and LiteLLM running
on localhost.

| Check | Result |
|---|---|
| GW-08 E2E smoke | passed |
| Parity smoke | passed |
| Embedding alias | `quimera_embed` |
| Temporary collection prefix | `gw08_embedding_migration_` |
| Synthetic chunks indexed | 4 |
| Chunks retrieved/used | 4 |
| Embedding/indexing latency | 314.7 ms |
| Retrieval latency | 27.4 ms |
| Generation latency | 4951.7 ms |
| Total pipeline latency | 4979.1 ms |
| Direct Ollama vs gateway cosine similarity | 1.000000 |
| Vector dimensions | 768 |

The first live attempt failed because the already-running LiteLLM process had
not been restarted after adding the `quimera_embed` alias. After restarting
LiteLLM with `infra/litellm/litellm_config.yaml`, `/v1/models` exposed both
`quimera_embed` and `local_embed`, and the GW-08 smoke passed.

Run live validation only with local services:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_gw08_embedding_migration.sh
```

Or run the guarded pytest smoke directly:

```bash
RUN_GW08_EMBEDDING_MIGRATION_SMOKE=1 \
RUN_GW08_EMBEDDING_PARITY_SMOKE=1 \
uv run pytest tests/smoke/test_rag_gateway_embedding_migration_smoke.py -v -s
```

## Manual Cleanup

GW-08 smoke uses temporary Qdrant collections named:

```text
gw08_embedding_migration_<short_uuid>
```

Cleanup is attempted in test teardown. If a run is interrupted, manually delete
only collections whose names start with `gw08_embedding_migration_`.
