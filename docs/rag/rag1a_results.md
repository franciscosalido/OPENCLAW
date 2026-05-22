# RAG-1A Sprint Decision Report

## Executive Summary

RAG-1A tested the foundation for hybrid retrieval in Quimera: dense retrieval as
the baseline, sparse retrieval as a lexical complement, and Python-side Weighted
RRF as the auditable fusion layer.

The sprint hypothesis is measurable, but the persistent PR-11 measurement
artifacts are not present in this branch. Therefore this report does not claim
that hybrid retrieval won or lost. The architectural decision is deferred until
`evaluation/results/dense_vs_hybrid_summary.json`,
`evaluation/results/dense_vs_hybrid_rows.csv`, and the visual report are
generated from the agreed benchmark.

The implementation evidence is present: deterministic RRF, hybrid Qdrant schema,
hybrid ingest, hybrid retriever, smoke wiring, comparator, and structured
retrieval logs. The measurement evidence is still `TBD`.

Decision proposed now: `inconclusive_collect_more_evidence`.

Next step: run the PR-11 comparator against the intended benchmark artifacts,
then update this report and the ADR with measured values.

## Hypothesis

Hybrid retrieval with dense + sparse + Weighted RRF should improve Recall@10 and
NDCG@5 over dense-only without exceeding the p95 latency multiplier threshold
defined by PR-11.

## Null Hypothesis

Hybrid retrieval does not improve Recall@10 or NDCG@5 by at least 3 percentage
points, or it exceeds 2.5x the p95 latency of dense-only retrieval.

## Measurement Sources

| Artifact | Purpose | Present |
|---|---|---|
| `evaluation/results/dense_vs_hybrid_summary.json` | aggregated metrics/verdict | no |
| `evaluation/results/dense_vs_hybrid_rows.csv` | per-query paired evidence | no |
| `evaluation/results/dense_vs_hybrid_report.md` | human-readable comparator report | no |
| `evaluation/results/dense_vs_hybrid_charts.svg` | visual explanation | no |
| retrieval logs PR-12 | latency/observability evidence | no persistent artifact |
| hybrid smoke PR-10 | E2E integration proof | implementation present; latest run result not embedded here |

Measurement artifacts are not present in this branch. All metric fields below are
therefore `TBD`.

## Method

| Field | Value |
|---|---|
| Corpus hash | `TBD` |
| Query count | `TBD` |
| Query categories | `TBD` |
| Qrels type | `TBD`; PR-11 supports graded doc_id relevance 0/1/2 |
| Dense baseline | dense-only retrieval |
| Hybrid config | dense + sparse + Python-side Weighted RRF |
| RRF profile | `TBD` |
| Qdrant server version | `TBD` |
| Qdrant client version | `TBD` |
| Collection used | `TBD` |
| `search_top_k` | `TBD` |
| `return_top_k` | `TBD` |
| Metrics | Precision@5, Recall@10, MRR, NDCG@5, latency p50/p95 |

## Dense Baseline

| Metric | Value |
|---|---:|
| Precision@5 | `TBD` |
| Recall@10 | `TBD` |
| MRR | `TBD` |
| NDCG@5 | `TBD` |
| p50 total_ms | `TBD` |
| p95 total_ms | `TBD` |

## Hybrid Result

| Metric | Value |
|---|---:|
| Precision@5 | `TBD` |
| Recall@10 | `TBD` |
| MRR | `TBD` |
| NDCG@5 | `TBD` |
| p50 total_ms | `TBD` |
| p95 total_ms | `TBD` |

## Dense vs Hybrid Delta

| Metric | Dense | Hybrid | Delta abs | Delta % | Winner |
|---|---:|---:|---:|---:|---|
| Recall@10 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| NDCG@5 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| MRR | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| p95 total_ms | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |

## Latency and Golden Signals

| Mode | p50 total_ms | p95 total_ms | search_ms avg | non_search_overhead_ms | chunks_returned avg | score_stats.rank1_gap avg |
|---|---:|---:|---:|---:|---:|---:|
| dense_only | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| hybrid | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |

Definitions:

- `search_ms`: observed retrieval search cost.
- `total_ms`: observed end-to-end retrieval pipeline cost.
- `non_search_overhead_ms`: `total_ms - search_ms`.
- `chunks_returned`: amount of evidence returned to downstream RAG.
- `top_k_scores` and `score_stats`: score shape signals for ranking strength and
  ambiguity.
- `score_stats.rank1_gap`: average separation between rank 1 and rank 2 scores;
  low or negative values require query-level inspection.

## Query Category Evidence

| Category | Delta Recall@10 | Delta NDCG@5 | Hybrid wins | Dense wins | Risk |
|---|---:|---:|---:|---:|---|
| lexical | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| semantic | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| hybrid | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| risk | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| macro | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |

## Top Gains and Regressions

Top 5 hybrid gains by query_id:

1. `TBD`
2. `TBD`
3. `TBD`
4. `TBD`
5. `TBD`

Top 5 hybrid regressions by query_id:

1. `TBD`
2. `TBD`
3. `TBD`
4. `TBD`
5. `TBD`

Query text must not be listed in this section.

## Retrieval Personality

Expected categories from PR-11:

- `lexical_boost`: sparse rank improves the fused result.
- `semantic_boost`: dense rank dominates the fused result.
- `agreement`: dense and sparse agree.
- `sparse_only_rescue`: hybrid recovers an item dense-only missed.
- `dense_only_rescue`: dense remains necessary and protects against sparse-only
  gaps.

Measured counts: `TBD`.

## Privacy and Logging Contract

The operational `query` requirement is represented by:

- `query_hash`
- `query_len`
- `query_is_redacted=true`

Default reports and retrieval logs must not contain:

- query literal
- chunk text
- document text
- prompt
- answer
- vector
- embedding
- raw payload

PR-12 structured events are designed around safe fields such as:

- `mode`
- `embed_dense_ms`
- `embed_sparse_ms`
- `search_ms`
- `total_ms`
- `top_k_scores`
- `score_stats`
- `fusion`
- `chunks_returned`

## Decision

Decision: `inconclusive_collect_more_evidence`.

Reason: PR-11 implementation exists, but persistent measurement artifacts are not
present in this branch. Without the comparator summary, rows, and visual report,
there is no defensible basis to promote hybrid retrieval or to conclude that it
failed.

If the later measured result shows hybrid improves quality within the latency
threshold, recommend gradual promotion of `quimera_knowledge_v2`:

1. Keep `quimera_knowledge` intact.
2. Keep `quimera_knowledge_v2` as the candidate collection.
3. Enable shadow traffic.
4. Promote first the query categories that show measured gains.
5. Monitor p95 `total_ms` and regressions by query category.
6. Only then consider making hybrid the default.

If the measured result does not improve, open an investigative issue before
RAG-1B:

- revise RRF weights
- validate sparse encoder/BM25 behavior
- evaluate `search_top_k` versus `return_top_k`
- expand or correct qrels
- analyze regressions by category
- review metadata and chunking

## Recommended Next Steps

1. Generate PR-11 artifacts under `evaluation/results/`.
2. Update this report with measured values only.
3. Update the ADR status from `Deferred` to `Accepted` or keep it `Deferred`.
4. Expand the query set before RAG-1B.
5. Add curated real queries only if explicitly permitted and sanitized.
6. Keep PR-12 structured logs enabled in local-safe evaluation.
7. Compare regressions by query category.
8. Tune RRF only through benchmark evidence.
9. Preserve rollback to `dense_only`.
10. Keep `quimera_knowledge` protected.

## Limitations

1. The current sprint benchmark is synthetic by design.
2. Qrels are limited and may not represent production information needs.
3. Local environment latency does not represent concurrent production load.
4. Latency has not been measured under real multi-agent contention.
5. Human relevance judgment may be absent or incomplete.
6. Local Qwen/Qwen3-related components may still require maturity in Docker.
7. The legacy `quimera_knowledge` collection has not been migrated.
8. Retrieval quality does not prove final LLM answer quality.
9. This experiment does not validate financial safety, suitability, or
   correctness for real investment decisions.
10. Missing PR-11 result artifacts prevent a final measured decision in this
   branch.

## Conditions for Reversal

| Condition | Threshold | Measurement |
|---|---|---|
| Hybrid recall drops below dense | Delta Recall@10 < -0.02 | PR-11 comparator |
| Hybrid NDCG drops below dense | Delta NDCG@5 < -0.02 | PR-11 comparator |
| Hybrid p95 latency too high | p95 multiplier > 2.5x | PR-11/PR-12 |
| Regression rate too high | dense wins > 25% of queries | PR-11 |
| Collection metadata drift | guard failure | PR-06/PR-09 |
| Query text leaks | any | PR-12 tests |

## Machine-Readable Decision Block

<!-- machine-readable: rag1a-decision-v1 -->
```json
{
  "schema_version": "rag1a-decision-v1",
  "sprint_id": "RAG-1A",
  "generated_at": "2026-05-21",
  "decision": "inconclusive_collect_more_evidence",
  "corpus_hash": null,
  "query_count": null,
  "dense_baseline": {
    "precision_at_5": null,
    "recall_at_10": null,
    "mrr": null,
    "ndcg_at_5": null,
    "latency_p50_ms": null,
    "latency_p95_ms": null
  },
  "hybrid_result": {
    "precision_at_5": null,
    "recall_at_10": null,
    "mrr": null,
    "ndcg_at_5": null,
    "latency_p50_ms": null,
    "latency_p95_ms": null
  },
  "deltas": {
    "recall_at_10_abs": null,
    "recall_at_10_pct": null,
    "ndcg_at_5_abs": null,
    "ndcg_at_5_pct": null,
    "latency_p95_multiplier": null,
    "dense_win_rate": null
  },
  "promotion": {
    "candidate_collection": "quimera_knowledge_v2",
    "promoted_collection": null,
    "protected_collection": "quimera_knowledge",
    "mode": "none",
    "requires_shadow_traffic": true
  },
  "privacy": {
    "includes_query_text": false,
    "includes_document_text": false,
    "includes_payload": false,
    "includes_vectors": false,
    "query_is_redacted": true
  }
}
```
