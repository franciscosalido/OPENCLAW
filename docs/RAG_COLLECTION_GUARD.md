# RAG Collection Metadata Guard

GW-09 adds a lightweight traceability guard for Qdrant collection embedding
metadata. It detects provenance drift; it does not migrate, reindex, heal,
delete, or recreate collections.

## Purpose

After GW-08, new controlled embedding paths can use:

```text
gateway_litellm_current
```

Older collections may still contain payloads created with:

```text
direct_ollama_current
```

Both can be legitimate, but they must not be mixed or silently confused. The
guard samples existing payload metadata and compares it with the active RAG
configuration.

## API

```python
check_collection_metadata(
    client,
    collection_name,
    active_backend="gateway_litellm_current",
    active_model="nomic-embed-text",
    active_dimensions=768,
    active_contract="openai_compatible_v1_embeddings",
    active_alias="quimera_embed",
    sample_size=10,
    strict=False,
)
```

The helper calls Qdrant `scroll` with:

```text
with_payload=True
with_vectors=False
```

Vectors are never requested.

## Behavior

- Empty collections return a zero-count sample with no warning.
- Backend mismatch logs a structured warning by default.
- Model mismatch logs a structured warning with `recommendation=reindex_required`.
- Contract mismatch logs a structured warning by default.
- Alias mismatch logs a structured warning by default.
- Missing embedding metadata logs a structured warning and usually means the
  collection predates GW-08 traceability metadata.
- Dimension mismatch always raises `EmbeddingDimensionMismatchError`.
- `strict=True` raises `CollectionMetadataMismatchError` for backend, model,
  contract, or alias mismatch.

The guard does not log chunk text, prompts, vectors, API keys, Authorization
headers, or secrets.

## Scope Boundaries

GW-09 does not integrate the guard into `QdrantVectorStore` or mutate storage
behavior. `QdrantVectorStore` remains a storage wrapper; the guard is a policy
and traceability helper.

GW-09 also does not touch `openclaw_knowledge`, reindex Qdrant, change the
default embedder, or enable any remote provider.

## Future Work

- GW-10: add `RagRunTrace` for per-query backend/model/collection traceability.
- GW-11: add structured embedding observability events with backend, alias,
  latency, chunk count, and error category.
