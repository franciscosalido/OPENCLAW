# Agent-0 Golden Harness

GW-18 adds an opt-in golden question benchmark harness for Agent-0.

The harness is a reproducible quality and latency baseline. It does not improve
model behavior, does not judge answers with another model, and does not change
runtime routing.

## Synthetic-Only Policy

Questions must be synthetic and educational. They must not include real
tickers, companies, funds, portfolios, private documents or user data.

The registry lives at:

```text
tests/golden/questions.yaml
```

Each question has:

- `id`
- `domain`
- `mode`
- `question`
- `rationale`

Supported modes:

- `chat`
- `rag`
- `json`

## Dry Run

Dry-run is fully offline and does not call LiteLLM, Ollama or Qdrant:

```bash
RUN_GOLDEN_HARNESS=1 uv run python scripts/run_golden_harness.py --dry-run
```

Custom output directory:

```bash
RUN_GOLDEN_HARNESS=1 uv run python scripts/run_golden_harness.py \
  --dry-run \
  --output-dir /tmp/openclaw_golden_reports
```

If `RUN_GOLDEN_HARNESS` is not `1`, the harness exits safely without running.

## Optional Live Run

Live mode may call the local Agent-0 runner. It remains local-only:

```bash
RUN_GOLDEN_HARNESS=1 uv run python scripts/run_golden_harness.py \
  --output-dir tests/golden/reports
```

Live mode requires the same local services as the selected runner modes. Reports
remain local artifacts and are ignored by Git.

## JSONL Result Schema

The JSONL report contains one safe object per question. It stores answer length
only, not answer text.

Fields include:

- `question_id`
- `domain`
- `mode`
- `route`
- `alias`
- `used_rag`
- `latency_ms`
- `decision_id`
- `estimated_remote_tokens_avoided`
- `answer_length_chars`
- `error_category`
- `fallback_applied`
- `fallback_reason`
- `quality_score`
- `skipped`
- `skipped_reason`

It never stores question text, answer text, prompts, chunks, vectors, payloads,
raw model responses, exception messages, API keys, Authorization headers or
secrets.

Skipped semantics are explicit: a result cannot be both skipped and failed. If
`skipped` is `true`, `error_category` must be absent.

## Summary Schema

The summary JSON includes:

- `run_id`
- `timestamp_utc`
- `total_questions`
- `passed`
- `failed`
- `skipped`
- `fallback_count`
- `mean_latency_ms_by_alias`
- `p95_latency_ms_by_alias`
- `total_estimated_remote_tokens_avoided`
- `quality_score_present`
- `model_under_test_aliases`

Alias names are semantic aliases only. Concrete model names are not recorded.

## Human Scoring Rubric

GW-18 does not implement LLM-as-judge.

Future human review may use this rubric:

- `0`: no answer or hard error
- `1`: answer present but off-topic or incomplete
- `2`: plausible and topically relevant
- `3`: accurate, well-reasoned, cites if RAG

The optional scoring helper is deferred to GW-19 to keep GW-18 focused on the
registry, report contract and comparison tool.

## Comparison

Compare two summary files:

```bash
uv run python scripts/compare_golden_runs.py \
  --baseline path/to/baseline_summary.json \
  --candidate path/to/candidate_summary.json \
  --latency-threshold-pct 20
```

The comparison exits non-zero only for hard regressions:

- pass rate decreases
- any per-alias mean latency regresses beyond the threshold

## Out Of Scope

- Remote providers
- Remote API calls
- LLM-as-judge
- Dashboards
- OpenTelemetry
- Prometheus or Grafana
- Qdrant mutation or reindexing
- Real data
