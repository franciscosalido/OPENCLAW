# Qdrant 1.18.0 Upgrade - Design

Status: draft
Runtime changes: none in Q18-01

## Architecture Position

Qdrant permanece o motor vetorial primario do Quimera para este mini-sprint.
PostgreSQL/pgvector fica para uma fase posterior.

RAG-1A ja definiu um contrato importante: Python `RRFFusion` continua sendo a
fonte de verdade matematica ate que uma comparacao controlada prove que uma
fusao nativa do Qdrant pode ser adotada sem regressao de qualidade,
determinismo ou auditabilidade.

## Why Qdrant 1.18

Qdrant 1.18 e candidato a avaliacao por trazer capacidades alinhadas ao
Quimera local-first:

- TurboQuant para compressao experimental de vetores.
- Add/delete named vectors em collections existentes.
- Deep memory reporting por componente via Web UI/API.
- Low memory mode para recuperacao em hosts com memoria restrita.
- Strict mode guardrails, incluindo `max_resident_memory_percent`.
- Dynamic CPU pool, conforme changelog, para workloads com alto I/O wait.
- Audit log improvements, incluindo query API e tracing IDs.
- Per-collection API metrics.
- Hybrid query support com RRF e DBSF ja documentado no Query API.

Essas features nao sao tratadas como ganho comprovado. Elas sao candidatas a
benchmark em Q18-02..Q18-07.

## Why Not PostgreSQL Now

| Dimensao | Qdrant 1.18 | PostgreSQL + pgvector |
|---|---|---|
| Upgrade path | versao do mesmo backend | novo backend/schema/ETL |
| API compatibility | qdrant-client upgrade | reescrita de store/retriever |
| Sparse vector support | named sparse vectors nativos | outro contrato |
| RRF fusion | Python-side ja testado; native experimental | SQL/pgvector exigiria novo comparador |
| Sprint cost | 1 mini-sprint | 3-4 sprints |
| Foco atual | retrieval engine capability | relational persistence consolidation |

PostgreSQL/pgvector deve ser reavaliado se:

- houver necessidade de ACID entre dados relacionais e vetoriais
- houver problema local single-node com mais de 10M vectors
- pgvector expuser hybrid/RRF estavel e competitivo para o caso Quimera
- joins, tenancy ou governanca relacional virarem requisito central
- Qdrant deixar de suportar named sparse vectors ou outro requisito critico

## Candidate Collections

Future benchmark and smoke PRs may use:

- `q18_benchmark_hybrid_*`
- `q18_smoke_*`
- `quimera_knowledge_v2_dev_*`

Never use for destructive reset without explicit human decision:

- `quimera_knowledge`
- `quimera_knowledge_v2`
- any non-prefixed collection
- any remote Qdrant host

## Named Vector Design

Patterns to evaluate:

- `dense` + `sparse` baseline
- `dense_new` for embedding migration
- `dense_qwen3_4b` future candidate
- `colbert` or future multivector field
- `sparse` lexical/BM25

Conceptual config only:

```python
NAMED_VECTORS = {
    "dense": {"size": 1024, "distance": "Cosine"},
    "dense_new": {"size": 1024, "distance": "Cosine"},
    "sparse": {"sparse": {}},
}
```

## Named Vector Create/Delete API Contract

Qdrant 1.13.x required named vectors to be defined when creating a collection.
Qdrant 1.18 documents schema-level add/remove operations for named vectors in an
existing collection.

Impact for Quimera:

- `dense_vector_name` and `sparse_vector_name` remain configurable.
- A future migration can add a candidate dense vector without recreating the
  whole collection.
- Deleting a vector definition is destructive for that vector data and must be
  restricted to benchmark/prefix collections.

## Candidate Tuning Profiles

### baseline_ram

No quantization, no on-disk vectors. Use as the comparability baseline.

### balanced_local

RAM-first, HNSW defaults, search params controlled by benchmark.

### low_memory

Vectors on disk plus HNSW on disk where supported. Expect lower memory pressure
and potential latency cost.

### scalar_quant

Scalar int8, `always_ram` selected by benchmark profile.

### turboquant_experimental

TurboQuant `bits4`, rescore true, experimental until Q18-07. Do not make this
the default without measured Recall@10/NDCG@5 and latency evidence.

## TurboQuant vs Scalar Assessment

For a conceptual 1024-dimensional dense vector:

- f32: `1024 * 4 bytes = 4096 bytes` before overhead
- scalar int8: `1024 * 1 byte = 1024 bytes` before overhead
- TurboQuant bits4: about `1024 * 4 / 8 = 512 bytes` before overhead

The Qdrant docs recommend testing TurboQuant on project data before committing.
Q18-07 decides; Q18-01 only records the candidate.

## Strict Mode Risk Analysis

| Operation | Current risk | Strict mode risk | Mitigation |
|---|---|---|---|
| arbitrary payload metadata | unknown keys | update rejection | validate payload schema |
| filters on non-indexed fields | doc_id/security filters | query rejection/perf | create payload indexes |
| sparse vector upsert | variable indices | unknown behavior | validate docs/API |
| named vector deletion | schema evolution | destructive misuse | prefix-only guard |
| batch search | accidental large requests | strict rejection | cap batch size in adapter |
| memory-heavy writes | local OOM | write rejection | handle typed operational failure |

## Memory Budget Estimate

Qdrant, Ollama and LiteLLM compete for local RAM. Low memory mode can help bring
a node up under memory pressure, but it can increase operational complexity and
may affect latency depending on storage/profile choices.

Baseline order-of-magnitude pressure before Q18-05 measurement:

| Component | Approximate local RAM pressure | Notes |
|---|---:|---|
| Qdrant idle/server baseline | 300-500 MB | before collection/vector growth |
| Ollama `qwen3:14b` | about 10 GB | model residency dominates local pressure |
| `nomic-embed-text` embedding model | about 512 MB | depends on runtime residency |
| LiteLLM gateway | about 256 MB | lightweight but still part of shared budget |
| Total shared pressure | about 12 GB | estimate only; Q18-05 must measure |

Q18 must not assume a fixed percentage improvement. It must record actual memory
reports and compare them against the same corpus/config.

## Fusion Design

Default:

- Python `RRFFusion` remains source of truth.

Experimental:

- Qdrant native Weighted RRF.
- Qdrant native DBSF as research-only.

Native Weighted RRF is only compared in Q18-06. It is not adopted in Q18-01.

## Observability Design

Future PRs should record:

- `qdrant_server_version`
- `qdrant_client_version`
- collection config
- quantization config
- memory report
- strict mode config
- on-disk flags
- HNSW params
- search params
- audit/tracing feature availability
- per-collection metrics availability

## Q18-04 Benchmark Schema Contract

Q18-04 fixes the benchmark schema for Q18-05/Q18-06/Q18-07:

| Field | Value |
|---|---|
| Collection | `quimera_benchmark_hybrid_118` |
| Dense vector | `dense`, 1024 dimensions, Cosine |
| Sparse vector | `sparse` |
| Schema version | `qdrant-hybrid-118-v1` |
| Snapshot | `docs/specs/qdrant-1-18-upgrade/benchmark_schema_snapshot.json` |

Q18-04 does not promote `quimera_knowledge_v2`, does not touch
`quimera_knowledge`, does not ingest points and does not benchmark.

Q18-04 RC-01 hardening notes:

- The spec is hashable for future cache/set use even though it stores payload
  index types behind an immutable mapping.
- Snapshot version metadata uses the Qdrant client `info()` call when a live
  client is available. If an intermediate proxy/client cannot expose server
  version, the value remains null and later benchmark gates must fail closed.
- The schema factory records future metrics and telemetry endpoints only. Q18-05
  must implement the actual scrape and decide tuning profiles from measured
  memory/latency data.
- Payload index validation is deliberately narrowed to `keyword` and `integer`
  for the benchmark schema. Adding `float`, `datetime` or other schemas is a
  future explicit schema change, not an implicit allowance.

## Rollback Decision Tree

| Failure mode | Local action | Rollback |
|---|---|---|
| `container_wont_start` | stop 1.18 container; inspect config only | re-pin future PR to 1.13.x |
| `api_breaking_change` | keep adapters behind compatibility layer | restore qdrant-client 1.13.2 |
| `collection_inaccessible` | do not mutate protected collections | delete only `q18_*` collections |
| `performance_regression` | preserve benchmark artifacts | return to baseline profile |
| `recall_regression` | keep Python RRF and dense baseline | block promotion in ADR |

Do not recreate embeddings if source corpus and deterministic chunk IDs exist.
Keep the retrieval API contract stable across rollback.
