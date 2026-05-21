# PR-09 Hybrid Ingest Handoff

## Status

PR-09 creates an offline-first hybrid ingest script for preparing points for
`quimera_knowledge_v2`.

The script does not create, delete, reset, migrate, or verify Qdrant
collections. It prepares named-vector points and can call an injected upsert
client only when `--execute` is explicitly enabled by a future integration
layer.

## Current Contract

- Default collection: `quimera_knowledge_v2`.
- Protected legacy collection: `quimera_knowledge`.
- Dense vector name: `dense`.
- Sparse vector name: `sparse`.
- Dense dimensions: `1024`.
- Default mode: dry-run.
- Real execute mode is blocked in PR-09 CLI until a real upsert adapter is
  explicitly wired in a later PR.
- Point IDs are deterministic UUID strings derived from chunk content.
- Payloads include metadata only, not chunk text or vectors.
- Summary output is safe and does not include raw text, vectors, embeddings,
  prompts, answers, or payload blobs.

## Residual Risks

### RISK-1: Collection Name Case Sensitivity

`assert_collection_is_safe_for_ingest()` intentionally protects the exact legacy
name after trimming whitespace. It does not casefold collection names.

That means `quimera_knowledge` is blocked, while `QUIMERA_KNOWLEDGE` is treated
as a different collection name.

This is acceptable for PR-09 because Qdrant collection names are operational
identifiers and the script should not silently rewrite operator input.

PR-10 should decide whether the real Qdrant adapter should:

- keep exact case-sensitive semantics, or
- add an explicit denylist for known legacy aliases.

### RISK-2: Sequential Embedding

`embed_chunks()` embeds dense vectors for all chunks, then sparse vectors for
all chunks. This is deliberately conservative and easy to test.

With real local Qwen/Ollama embedding, this will be the main throughput
bottleneck.

PR-10 should introduce controlled concurrency with a semaphore, for example:

```python
async def bounded_embed(
    chunks: Sequence[Chunk],
    *,
    concurrency: int,
) -> list[EmbeddingResult]:
    ...
```

The implementation must keep deterministic output ordering even when execution
is concurrent.

### RISK-3: Destination Schema Is Not Verified

PR-09 checks that the target collection is not the protected legacy collection.
It does not check that `quimera_knowledge_v2` exists or that it has the expected
named vectors:

- dense: 1024 dimensions, cosine
- sparse: sparse vector without server-side IDF modifier

PR-10 must add a preflight check in the real upsert adapter before sending any
points:

```python
async def assert_hybrid_collection_ready(
    *,
    collection_name: str,
    dense_vector_name: str,
    sparse_vector_name: str,
    dense_dimensions: int,
) -> None:
    ...
```

The preflight should fail before any upsert if the schema does not match.

### RISK-4: Demo Sparse Embedder Is Not Production BM25

`_DeterministicSparseEmbedder` is only for dry-run demos and tests. It now emits
unique sparse indices, but it is not BM25 and must not be used as production
retrieval semantics.

PR-10 should wire the real sparse embedder from the sparse component and keep
the deterministic embedder only for tests/dry-run demos.

## PR-10 Recommendations

1. Add a real Qdrant upsert adapter that only calls `upsert`.
2. Add schema preflight before any upload.
3. Keep `dry-run` as the default path.
4. Require explicit `--execute` plus a real adapter for upload.
5. Keep legacy collection protection in both script and adapter.
6. Add bounded concurrency for embedding with stable output order.
7. Keep summaries content-free and vector-free.
8. Add an integration smoke test guarded by an environment variable.
9. Do not add collection creation/deletion to the ingest script.
10. Keep payload text out of PR-09 ingest payloads; retrieval payload policy
    should remain owned by the store/retriever integration layer.
