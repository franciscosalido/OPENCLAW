# Qdrant 1.18 Upgrade Results

## Executive Summary

Q18-07 remains inconclusive because required benchmark artifacts are missing; Python RRFFusion remains default, TurboQuant remains experimental, and PostgreSQL/GraphRAG remain out of scope.

This report is artifact-only by default. It records missing evidence as missing
evidence and never invents benchmark numbers.

## Hypotheses

- Qdrant 1.18 improves local-first observability/performance.
- `balanced_local` is safer default than TurboQuant before measurement.
- TurboQuant may reduce memory but requires quality benchmark evidence.
- Native RRF may reduce app-side work but must match Python RRFFusion behavior.

## Evidence Sources

- Q18-04 schema contract: `quimera_benchmark_hybrid_118`.
- Q18-05 tuning profiles: `baseline_ram`, `balanced_local`,
  `turboquant_experimental`.
- Q18-06 native RRF comparison contracts.
- Historical Qdrant 1.13 baseline present: `false`.

## Methodology

Each scenario compares two named artifact profiles. Quality metrics are higher
is better. Latency and resource metrics are lower is better. Missing values are
reported as `null`/TBD and excluded from promotion claims.

## Scenario Matrix

| Scenario | Profile A | Profile B | Decision hint | Evidence complete |
|---|---|---|---|---|
| `qdrant_113_vs_118_baseline` | `qdrant_113_historical_baseline` | `qdrant_118_baseline_ram` | `inconclusive_missing_evidence` | false |
| `qdrant_118_baseline_vs_balanced` | `qdrant_118_baseline_ram` | `qdrant_118_balanced_local` | `inconclusive_missing_evidence` | false |
| `qdrant_118_python_rrf_vs_native_rrf` | `qdrant_118_python_rrf` | `qdrant_118_native_rrf` | `inconclusive_missing_evidence` | false |
| `qdrant_118_no_quant_vs_turboquant` | `qdrant_118_no_quantization` | `qdrant_118_turboquant_experimental` | `inconclusive_missing_evidence` | false |
| `qdrant_118_dense_only_vs_hybrid` | `qdrant_118_dense_only` | `qdrant_118_hybrid` | `inconclusive_missing_evidence` | false |

## Results

Quality, latency and resource deltas are stored in
`evaluation/results/qdrant_118_benchmark_summary.json` when generated.

## Visual Summary

See `evaluation/results/qdrant_118_benchmark_charts.svg`.

## Decision

`inconclusive_missing_evidence`

Python RRFFusion default: `true`.
Native RRF decision: `keep_python_rrf_default`.
TurboQuant decision: `accept_turboquant_experimental_only`.

## Why PostgreSQL / GraphRAG Are Out Of Scope

Q18 decides Qdrant engine, tuning and fusion behavior. PostgreSQL, pgvector and
GraphRAG require a separate backend/data-model sprint and are explicitly outside
this cycle.

## Rollback

- Return to the previous accepted Qdrant profile.
- Keep Python RRFFusion default.
- Disable TurboQuant.
- Use artifact-only comparison until live evidence is regenerated.
- Revert Qdrant version only in a dedicated rollback PR.

## Limitations

- Historical 1.13 baseline artifacts may be absent.
- Local measurements do not represent production concurrency.
- Deep memory reporting may be unavailable in some artifacts.
- TurboQuant requires a broader corpus before adoption.
- Native RRF may diverge in tie-break behavior even with high overlap.

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
