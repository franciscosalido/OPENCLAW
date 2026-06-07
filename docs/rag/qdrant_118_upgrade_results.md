# Qdrant 1.18 Upgrade Results

## Executive Summary

Qdrant 1.18 promotion is deferred due to measured regression; retain the previous safe profile and Python RRFFusion default.

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
- Historical Qdrant 1.13 baseline present: `true`.

## Documentation Paths

The canonical ADR directory in this repository is `docs/ADR`. Lowercase
`docs/adr` references should be treated as legacy/case-insensitive aliases.

## Methodology

Each scenario compares two named artifact profiles. Quality metrics are higher
is better. Latency and resource metrics are lower is better. Missing values are
reported as `null`/TBD and excluded from promotion claims.

## Scenario Matrix

| Scenario | Profile A | Profile B | Decision hint | Evidence complete |
|---|---|---|---|---|
| `qdrant_113_vs_118_baseline` | `qdrant_113_historical_baseline` | `qdrant_118_baseline_ram` | `defer_due_to_regression` | true |
| `qdrant_118_baseline_vs_balanced` | `qdrant_118_baseline_ram` | `qdrant_118_balanced_local` | `defer_due_to_regression` | true |
| `qdrant_118_python_rrf_vs_native_rrf` | `qdrant_118_python_rrf` | `qdrant_118_native_rrf` | `keep_python_rrf_default` | true |
| `qdrant_118_no_quant_vs_turboquant` | `qdrant_118_no_quantization` | `qdrant_118_turboquant_experimental` | `defer_due_to_regression` | true |
| `qdrant_118_dense_only_vs_hybrid` | `qdrant_118_dense_only` | `qdrant_118_hybrid` | `accept_qdrant_118_baseline` | true |

## Results

Quality, latency and resource deltas are stored in
`evaluation/results/qdrant_118_benchmark_summary.json` when generated.

## Visual Summary

See `evaluation/results/qdrant_118_benchmark_charts.svg`.

## Decision

`defer_due_to_regression`

Python RRFFusion default: `true`.
Native RRF decision: `keep_python_rrf_default`.
TurboQuant decision: `accept_turboquant_experimental_only`.

## D2P Update: Qdrant Server 1.18.2

The benchmark matrix above was produced for Qdrant Server `1.18.0`; those
numbers must not be rewritten as `1.18.2` evidence.

ADR-D2P-018 and PKD-D2P-00Y now target Qdrant Server `1.18.2` for local-first
runtime evaluation because it is the latest stable patch in the accepted
`1.18.x` family. The Python client dependency requires `qdrant-client>=1.18`,
with `uv.lock` currently resolved at `1.18.0`.

Qwen3 benchmarks should be repeated against server version `1.18.2`, and new
artifacts should record `qdrant_server_version=1.18.2`. Python RRFFusion remains
the default, TurboQuant remains experimental, and PostgreSQL/GraphRAG remain
outside this cycle.

If older run JSONs show `qdrant_server_version="1.18.0"`, treat that as a
client-version annotation unless a live readiness or metrics snapshot proves the
remote server version. New Q18/Qwen3 benchmarks should use
`scripts/collect_qdrant_metrics_snapshot.py` before and after runs so
`peak_ram_mb`/resident memory evidence is not left as `null`.

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
- Previous runs had `peak_ram_mb=null`; storage decisions need metrics snapshots
  before promotion.
- TurboQuant requires a broader corpus before adoption.
- Native RRF may diverge in tie-break behavior even with high overlap.

## Machine-readable block

<!-- machine-readable: qdrant-118-decision-v1 -->
```json
{
  "baseline_113_present": true,
  "decision": "defer_due_to_regression",
  "native_rrf": "keep_python_rrf_default",
  "postgresql": "out_of_scope",
  "python_rrf_default": true,
  "recommended_default_profile": null,
  "schema_version": "qdrant-118-decision-v1",
  "turboquant": "experimental_only"
}
```
