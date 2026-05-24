# ADR-0XX: Qdrant 1.18 Upgrade Decision

Status: Proposed

## Context

Q18 evaluated Qdrant 1.18 as the next local-first vector backend for Quimera
after RAG-1A established dense+sparse hybrid retrieval and Python RRFFusion.

## Decision

Q18-07 remains inconclusive because required benchmark artifacts are missing; Python RRFFusion remains default, TurboQuant remains experimental, and PostgreSQL/GraphRAG remain out of scope.

## Evidence

Evidence is recorded in `docs/rag/qdrant_118_upgrade_results.md` and, when
generated, `evaluation/results/qdrant_118_benchmark_summary.json`.

## Alternatives Considered

1. Keep Qdrant 1.13.x historical baseline.
2. Accept Qdrant 1.18 baseline profile.
3. Accept Qdrant 1.18 `balanced_local`.
4. Promote native Qdrant RRF.
5. Migrate to PostgreSQL/pgvector or GraphRAG now.

## Consequences

- Python RRFFusion remains the default unless native RRF earns explicit strong
  evidence.
- TurboQuant remains experimental unless quality, latency and memory thresholds
  are all satisfied.
- PostgreSQL/GraphRAG stay outside Q18.

## Default Config

Recommended profile: `TBD`.

## Python vs Native RRF

Native RRF decision: `keep_python_rrf_default`.

## TurboQuant Decision

TurboQuant decision: `accept_turboquant_experimental_only`.

## PostgreSQL/GraphRAG Scope

`out_of_scope_for_q18`

## Rollback

1. Keep Python RRFFusion.
2. Disable TurboQuant.
3. Return to the previous accepted profile.
4. Re-run Q18-07 artifact-only comparison.
5. Revert Qdrant version only through a dedicated rollback PR.

## Conditions for Reversal

- Recall@10 delta below `-0.01`.
- NDCG@5 delta below `-0.01`.
- p95 latency multiplier above `2.5`.
- Native RRF tie-break regressions appear.
- Memory reporting contradicts local-first resource goals.

## Follow-ups

- Generate real Q18 artifacts with `RUN_QDRANT_118_BENCHMARK=1`.
- Expand corpus and query categories before any production-style promotion.
- Keep PostgreSQL/GraphRAG as a future architecture discussion, not Q18 scope.

## Machine-readable block

<!-- machine-readable: qdrant-118-decision-v1 -->
```json
{
  "baseline_113_present": false,
  "decision": "inconclusive_missing_evidence",
  "native_rrf": "keep_python_rrf_default",
  "postgresql": "out_of_scope",
  "python_rrf_default": true,
  "recommended_default_profile": null,
  "schema_version": "qdrant-118-decision-v1",
  "turboquant": "experimental_only"
}
```
