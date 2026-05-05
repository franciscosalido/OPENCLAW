# Gateway-2 Sprint Handoff

Gateway-2 is the performance measurement and controlled optimization sprint
for the local-first RAG path. It closes with an offline baseline freeze and
regression gate.

## Completed PRs

- G2-01: per-segment RAG latency baseline in `RagRunTrace`
- G2-02: configurable whole-chunk context budget cap
- G2-03: local_rag generation budget and concise-answer discipline
- G2-04: cold/warm/degraded latency separation
- G2-05: opt-in Ollama `keep_alive` model residency for `local_rag`
- G2-06: local-only candidate alias comparison without default promotion
- G2-07: frozen Gateway-2 baseline and offline regression gate

## Final Baseline

Official artifacts:

- `tests/golden/baseline/gateway2_baseline_summary.json`
- `tests/golden/baseline/gateway2_baseline_results.jsonl`
- `tests/golden/baseline/gateway2_baseline_scores.jsonl`
- `tests/golden/baseline/gateway2_regression_thresholds.yaml`

The baseline is grouped by alias and run type. `cold_start`, `warm_model`, and
`degraded_qdrant` must not be averaged into one latency number.

## Regression Gate

Use:

```bash
uv run python scripts/compare_golden_runs.py \
  --verify-only tests/golden/baseline/gateway2_baseline_summary.json
```

and for candidates:

```bash
uv run python scripts/compare_golden_runs.py \
  --baseline tests/golden/baseline/gateway2_baseline_summary.json \
  --candidate <candidate-summary.json> \
  --thresholds tests/golden/baseline/gateway2_regression_thresholds.yaml
```

The gate is offline and deterministic. It does not call Ollama, LiteLLM,
Qdrant, or remote providers.

## Optimized

- Context size became configurable and rollback-safe.
- Generation length became configurable and rollback-safe.
- Model residency became configurable and observable for `local_rag`.
- Candidate alias comparison became possible without changing defaults.

## Deferred

- Alias promotion requires a future PR.
- Remote providers require a future ADR and remain disabled.
- FastAPI, MCP, OpenTelemetry, dashboards, and production ingestion remain out
  of scope.
- `openclaw_knowledge` must not be mutated without an explicit sprint.

## Next Sprint Entry Point

Gateway-3 should start from the frozen baseline. Any performance or quality
claim should compare against the official Gateway-2 artifacts and pass the
offline regression gate before live proof is considered.
