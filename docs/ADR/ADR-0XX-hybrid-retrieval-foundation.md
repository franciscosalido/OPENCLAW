# ADR-0XX: Hybrid Retrieval Foundation

## Status

Deferred.

The hybrid retrieval implementation is present, but the persistent PR-11
measurement artifacts are not present in this branch. This ADR must not be
accepted until the dense-only versus hybrid comparator outputs are generated and
reviewed.

## Date

2026-05-21

## Context

RAG-1A built the local-first hybrid retrieval foundation for Quimera:

- a new hybrid Qdrant collection contract for `quimera_knowledge_v2`
- named dense and sparse vectors
- deterministic Python-side Weighted RRF fusion
- an async hybrid retriever
- a controlled hybrid ingest script
- an opt-in smoke test path
- a dense-only versus hybrid comparator
- structured retrieval observability logs

The architectural question is:

> Should Quimera promote hybrid dense+sparse retrieval as the next retrieval
> foundation, or should it keep dense-only until more evidence is collected?

The decision must be based on measured retrieval quality and latency, not on
implementation success alone.

## Decision Drivers

1. Hybrid must improve Recall@10 and NDCG@5 over dense-only.
2. Hybrid must not exceed the PR-11 p95 latency multiplier threshold.
3. Regressions must be evaluated query-by-query, not only by aggregate averages.
4. Query categories must be analyzed separately.
5. `quimera_knowledge` must remain protected.
6. `quimera_knowledge_v2` must be promoted only gradually.
7. Retrieval logs must not leak query text, chunk text, payloads, vectors,
   embeddings, prompts or answers.

## Evidence Required

Before this ADR can become `Accepted`, the following artifacts must exist and be
reviewed:

| Artifact | Required | Current status |
|---|---:|---|
| `evaluation/results/dense_vs_hybrid_summary.json` | yes | absent in this branch |
| `evaluation/results/dense_vs_hybrid_rows.csv` | yes | absent in this branch |
| `evaluation/results/dense_vs_hybrid_report.md` | yes | absent in this branch |
| `evaluation/results/dense_vs_hybrid_charts.svg` | yes | absent in this branch |
| PR-12 retrieval log contract | yes | implementation present |
| PR-10 smoke evidence | recommended | implementation present; latest run not embedded here |

## Decision

Defer promotion.

The project should not yet declare hybrid retrieval as the default foundation.
The implementation is ready for measured evaluation, but the measured artifacts
are missing from this branch. The current decision is therefore:

```text
inconclusive_collect_more_evidence
```

## Considered Options

1. **Keep dense-only as the default indefinitely** — lowest regression risk, but
   it may leave lexical gains from sparse retrieval unused.
2. **Promote hybrid immediately as the default** — rejected for now because the
   persistent PR-11 measurement artifacts are absent in this branch.
3. **Promote hybrid gradually by query category** — preferred if PR-11 artifacts
   prove that hybrid clears quality and latency thresholds.
4. **Investigate before RAG-1B without promotion** — active now, and also the
   fallback if hybrid does not clear thresholds.

Current decision: option 4 applies now. Option 3 applies only after measured
PR-11 artifacts support gradual promotion.

## Promotion Rule

If the later PR-11 artifacts show hybrid retrieval clears the thresholds:

1. Keep `quimera_knowledge` intact.
2. Keep `quimera_knowledge_v2` as the candidate collection.
3. Enable shadow traffic before default traffic.
4. Promote first the query categories with measured wins.
5. Monitor PR-12 structured fields:
   - `mode`
   - `query_hash`
   - `query_len`
   - `embed_dense_ms`
   - `embed_sparse_ms`
   - `search_ms`
   - `total_ms`
   - `top_k_scores`
   - `score_stats`
   - `fusion`
   - `chunks_returned`
6. Keep rollback to `dense_only`.

## Investigation Rule

If hybrid does not improve or exceeds latency limits, open an investigative
issue before RAG-1B covering:

- RRF weight calibration
- sparse encoder/BM25 validation
- `search_top_k` versus `return_top_k`
- qrels quality and coverage
- regressions by query category
- metadata and chunking effects

## Consequences

Positive:

- The implementation can be evaluated without changing the retrieval default.
- The legacy collection remains protected.
- Structured logs create a privacy-safe operational audit trail.
- The decision remains falsifiable.

Negative:

- Hybrid retrieval is not yet promoted.
- The sprint is implementation-complete but measurement-incomplete until PR-11
  artifacts are generated.
- RAG-1B should not depend on hybrid being default without this ADR being
  updated.

## Observability Contract

The operational requirement for `query` is represented as:

- `query_hash`
- `query_len`
- `query_is_redacted=true`

The structured retrieval event must not include:

- query literal
- chunk text
- document text
- raw payload
- prompt
- answer
- vector
- embedding

This keeps observability useful for latency and ranking diagnosis while
preserving the local-first privacy posture.

## Follow-ups

1. Generate the PR-11 comparator artifacts under `evaluation/results/`.
2. Update `docs/rag/rag1a_results.md` with measured values.
3. Revisit this ADR status after Cowork reviews the measured numbers.
4. If hybrid clears thresholds, define the shadow-traffic rollout for
   `quimera_knowledge_v2`.
5. If hybrid does not clear thresholds, open the investigative issue before
   RAG-1B.

## Rollback

Rollback remains simple because hybrid is not yet the default:

1. Keep dense-only as the production/default path.
2. Do not delete `quimera_knowledge_v2` automatically.
3. Do not mutate `quimera_knowledge`.
4. Disable hybrid traffic by mode selection.
5. Continue recording safe retrieval logs for dense-only.

## Reversal Conditions

| Condition | Threshold | Measurement |
|---|---|---|
| Hybrid recall drops below dense | Delta Recall@10 < -0.02 | PR-11 comparator |
| Hybrid NDCG drops below dense | Delta NDCG@5 < -0.02 | PR-11 comparator |
| Hybrid p95 latency too high | p95 multiplier > 2.5x | PR-11/PR-12 |
| Regression rate too high | dense wins > 25% of queries | PR-11 |
| Collection metadata drift | guard failure | PR-06/PR-09 |
| Query text leaks | any | PR-12 tests |

## Links

- Sprint report: `docs/rag/rag1a_results.md`
- Comparator: `evaluation/compare_dense_vs_hybrid.py`
- Retrieval logger: `backend/rag/retrieval_logger.py`
- RRF fusion: PR-07, `backend/rag/fusion.py`
- Hybrid retriever: PR-08, `backend/rag/hybrid_retriever.py`
- Hybrid ingest: PR-09, `scripts/rag_ingest_hybrid.py`

## Machine-Readable Decision Block

<!-- machine-readable: rag1a-adr-decision-v1 -->
```json
{
  "schema_version": "rag1a-adr-decision-v1",
  "adr": "ADR-0XX-hybrid-retrieval-foundation",
  "status": "Deferred",
  "decision": "inconclusive_collect_more_evidence",
  "selected_option_now": 4,
  "future_promotion_option": 3,
  "candidate_collection": "quimera_knowledge_v2",
  "promoted_collection": null,
  "protected_collection": "quimera_knowledge",
  "requires_pr11_artifacts": true,
  "privacy": {
    "query_is_redacted": true,
    "includes_query_text": false,
    "includes_document_text": false,
    "includes_payload": false,
    "includes_vectors": false
  }
}
```
