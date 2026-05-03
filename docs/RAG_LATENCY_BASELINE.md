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

Allowed `run_context` labels:

- `cold_start`
- `warm_model`
- `degraded_qdrant`

Normal runtime may leave `run_context` unset. Baseline runs should label
cold/warm/degraded explicitly so reports are distinguishable without rerunning.

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

Serialization uses explicit allowlists and optional scalar fields only.

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
