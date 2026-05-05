# Gateway-2 Baseline

Gateway-2 closes with a frozen offline RAG latency baseline and a regression
gate. The gate is not an optimizer and does not call Ollama, LiteLLM, Qdrant or
any remote service.

## Official Artifacts

Tracked baseline artifacts live in `tests/golden/baseline/`:

- `gateway2_baseline_summary.json`
- `gateway2_baseline_results.jsonl`
- `gateway2_baseline_scores.jsonl`
- `gateway2_regression_thresholds.yaml`

Generated reports must go to ignored directories such as `reports/golden/`,
`reports/gateway2/`, `reports/ci/`, or a temporary path under `/tmp`.

## Required Fields

The summary records:

- `run_id`
- `timestamp_utc`
- `sprint`
- `source_commit`
- `branch`
- `question_fixture_hash`
- `golden_harness_version`
- `thresholds_version`
- `summary_by_alias_and_run_type`

Each JSONL result records:

- `question_id`
- `question_fixture_hash`
- `alias`
- `run_type`
- `total_ms`
- `citation_present`
- `answer_length_chars`
- `estimated_remote_tokens_avoided`

Optional metrics include `generation_ms`, `prompt_eval_duration_ms`,
`eval_duration_ms`, `load_duration_ms`, `ollama_eval_count`,
`tokens_per_second`, `fallback_applied`, and `quality_score`. If an optional
Ollama metric is unavailable, the row must include a safe
`metric_unavailable_reason`.

## Run Type Separation

Gateway-2 reports must keep these run types separate:

- `cold_start`
- `warm_model`
- `degraded_qdrant`

The gate rejects reports that average cold and warm latency into one top-level
metric. Latency comparisons are made only within the same alias and run type.

## Regression Gate

Verify the official baseline offline:

```bash
uv run python scripts/compare_golden_runs.py \
  --verify-only tests/golden/baseline/gateway2_baseline_summary.json
```

Compare a candidate against the official baseline:

```bash
uv run python scripts/compare_golden_runs.py \
  --baseline tests/golden/baseline/gateway2_baseline_summary.json \
  --candidate /tmp/openclaw_g2_candidate/gateway2_candidate_summary.json \
  --thresholds tests/golden/baseline/gateway2_regression_thresholds.yaml
```

For Gateway-2 summaries, `--thresholds` is required. The older comparison mode
without `--thresholds` remains only for pre-Gateway-2 golden summaries that use
legacy fields such as `total_questions`, `passed`, and
`mean_latency_ms_by_alias`.

Exit codes:

- `0`: pass
- `2`: schema or sanitization failure
- `3`: citation or quality failure
- `4`: latency regression
- `5`: fixture or config mismatch
- `6`: baseline/candidate incompatibility

## Hard Gates

The gate fails on:

- missing or mismatched `question_fixture_hash`
- missing or invalid `run_type`
- mixed cold/warm aggregate latency
- prohibited serialized keys or sensitive value markers
- RAG citation regression
- configured quality regression
- configured latency regression

Citation enforcement is controlled by each result row's `citation_expected`
field and by baseline-to-candidate regression from `citation_present=true` to
`false`. It is intentionally not controlled by
`gateway2_regression_thresholds.yaml` in G2-PR07.

It never stores prompt text, question text, answer text, chunks, vectors,
payloads, headers, API keys, raw exceptions, tracebacks, usernames, local paths,
or model weight paths.

## Baseline Update Policy

Updating the official baseline requires a deliberate baseline-only change:

1. Generate a candidate report with the current golden question set.
2. Compare it against the official baseline using the gate command above.
3. Review citation and quality manually; do not use LLM-as-judge.
4. Commit only sanitized baseline artifacts in the baseline update commit.
5. Do not include code changes in the same commit.
6. Keep `cold_start`, `warm_model`, and `degraded_qdrant` separated.

Any future change that promotes an alias, changes prompts, changes context
budget, changes generation budget, changes keep_alive behavior, or changes
retrieval must arrive in a separate PR with its own rationale.
