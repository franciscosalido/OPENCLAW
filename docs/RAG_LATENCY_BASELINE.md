# RAG Latency Baseline

G2-01 establishes a measurement-only RAG latency baseline. It does not optimize
retrieval, prompts, generation, models, aliases, timeouts, fallback behavior or
Qdrant configuration.

## Hypothesis

If `local_rag` total latency is around 32 seconds, at least 80% of the latency
is expected to be concentrated in model generation and prompt evaluation, not in
query embedding, Qdrant retrieval or context packing.

G2-01 only measures this hypothesis. Any optimization belongs to a later G2 PR.

## Segment Boundaries

All durations use `time.perf_counter()` wrappers around existing calls.

| Segment | Starts | Ends |
|---|---|---|
| `routing_ms` | before `decide_route()` | after `RouterDecision` exists |
| `embedding_ms` | before query embedding call | after query vector is returned |
| `retrieval_ms` | before Qdrant/vector-store search | after raw top-k results return |
| `context_pack_ms` | before mapping/dedup/truncation/packing | after final packed chunks are selected |
| `prompt_build_ms` | before prompt builder | after final message/prompt object is built |
| `generation_ms` | before `GatewayChatClient`/`LocalGenerator` call | after model response is returned |
| `total_ms` | at outer RAG run start | after final RAG result object is produced |

`total_ms` is measured directly with its own outer timer. It is not computed as
the sum of segment fields.

The current `LocalRagPipeline` does not own Agent-0 route selection. Direct
pipeline traces record `routing_ms=None` — not measured at this layer, not
zero. Agent-level routing correlation via `decision_id` is a future
integration point in the Agent-0 runner.

## Trace Fields

`RagRunTrace` keeps the older provenance fields and adds optional measurement
fields:

- `routing_ms`
- `embedding_ms`
- `retrieval_ms`
- `context_pack_ms`
- `prompt_build_ms`
- `generation_ms`
- `total_ms`
- `run_context`

G2-02 adds optional context budget metadata:

- `context_budget_enabled`
- `context_budget_applied`
- `context_chunks_retrieved`
- `context_chunks_used`
- `context_chunks_dropped`
- `context_budget_max_chunks`
- `context_estimated_tokens_used`

These fields are counts only. They make the whole-chunk context cap observable
without logging chunks or prompt text.

G2-03 adds optional generation budget metadata:

- `answer_length_chars`
- `answer_token_estimate`
- `generation_budget_enabled`
- `generation_budget_applied`
- `generation_budget_max_tokens`
- `conciseness_instruction_applied`

These fields make answer length discipline observable without serializing the
answer itself.

Allowed `run_context` labels:

- `cold_start`
- `warm_model`
- `degraded_qdrant`

Normal runtime may leave `run_context` unset. Baseline runs should label
cold/warm/degraded explicitly so reports are distinguishable without rerunning.

G2-04 makes the report-level label mandatory as `run_type`. New baseline
records without `run_type` are invalid. `run_context` remains the pipeline trace
label, while `run_type` is the benchmark report contract.

## Ollama Metrics

`RagRunTrace` can store native Ollama metric fields only if they are already
available in response metadata:

- `total_duration`
- `load_duration`
- `prompt_eval_count`
- `prompt_eval_duration`
- `eval_count`
- `eval_duration`

Duration values are converted from nanoseconds to milliseconds.

Current LiteLLM chat calls return normalized answer text only, so native Ollama
metrics are not available in normal `local_rag` traces. G2-01 records
`ollama_metrics_available=false` in that case.

Do not bypass LiteLLM, call Ollama directly, duplicate generation calls, or log
prompt/answer text to recover these metrics.

G2-04 preserves native Ollama metrics in baseline reports when they are already
available in `RagRunTrace`, including `ollama_load_duration_ms`,
`ollama_prompt_eval_duration_ms`, `ollama_eval_duration_ms`, and
`ollama_eval_count`. If they are unavailable, reports use safe enum-style
reasons only:

- `not_forwarded_by_gateway`
- `not_present_in_response`
- `not_applicable_degraded`
- `unknown`

`model_load_observed` is derived from `ollama_load_duration_ms > 500.0`. If
`ollama_load_duration_ms` is unavailable, `model_load_observed` is `null`.

## Safety

Latency traces must never include:

- prompt text
- question/raw user input
- answer text
- chunks or chunk text
- vectors or embeddings
- Qdrant payloads
- API keys, Authorization headers, tokens, passwords or secrets
- raw model responses
- raw exceptions, exception messages or tracebacks
- model weight paths

## Generation Budget Follow-up

G2-03 targets the measured `generation_ms` segment by allowing a config-driven
`local_rag` max-token cap and optional concise-answer instruction. It does not
change retrieval, context packing, Qdrant, model aliases, JSON mode, default
chat behavior, or fallback behavior.

See `docs/RAG_GENERATION_BUDGET.md` for the rollback-safe configuration and
validation contract.

Serialization uses explicit allowlists and optional scalar fields only.

## G2-04 Cold/Warm/Degraded Separation

G2-04 is measurement-only. It does not tune `keep_alive`, preload models, unload
models, change model config, change aliases, mutate Qdrant, alter retrieval, or
change fallback behavior.

The baseline command remains opt-in:

```bash
RUN_RAG_LATENCY_BASELINE=1 uv run python scripts/run_rag_latency_baseline.py \
  --output-dir /tmp/openclaw_g2_cold_warm
```

Generated reports include:

- one record per `run_type`;
- `alias`;
- safe model name;
- hardware snapshot;
- Ollama metric availability;
- model residency check result from read-only Ollama `/api/ps`;
- grouped latency aggregates by alias and `run_type`.

The `/api/ps` residency check is best-effort and local-only. It uses
`OLLAMA_API_BASE` when present, refuses non-local URLs, and records `null` if
the check is unavailable. It does not fail the whole benchmark just because
`/api/ps` is missing.

Cold start is operational and best-effort unless the operator ensures the model
is not already resident. Warm-model results are meaningful only when model
residency is observed or `ollama_load_duration_ms` indicates no load cost.

`cold_start`, `warm_model`, and `degraded_qdrant` numbers must never be averaged
into one global latency number. Reports group `mean_total_ms`, `p50_total_ms`,
and `p95_total_ms` by alias and `run_type`.

Existing reports can be validated without live services:

```bash
uv run python scripts/run_rag_latency_baseline.py \
  --verify-only /tmp/openclaw_g2_cold_warm/<report>.json
```

`degraded_qdrant` is isolated from successful `local_rag` runs. It exists to
verify failure/degradation measurement shape, not to represent normal RAG
quality or latency.

## Baseline Runs

The merge criterion for G2-01 is that the trace schema can represent three
baseline contexts:

- cold start
- warm model
- degraded Qdrant

The dedicated 3-run baseline command is deferred to G2-02 to keep this PR purely
focused on trace schema, segment boundaries and pipeline instrumentation. Until
then, operators can inspect `rag_run_trace` log records from normal local RAG
runs and verify the new segment fields.

Generated baseline artifacts, when introduced later, must be opt-in and ignored
by Git.
