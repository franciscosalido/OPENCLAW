# RAG Alias Comparison

G2-PR06 adds an opt-in benchmark for comparing local-only RAG generation
aliases against the current `local_rag` baseline.

This is comparison infrastructure only. It does not promote a candidate alias,
change defaults, change prompts, change retrieval, mutate Qdrant, alter context
budget, alter generation budget, alter keep_alive behavior, or enable remote
providers.

## Command

```bash
RUN_RAG_ALIAS_COMPARISON=1 uv run python scripts/run_rag_alias_comparison.py \
  --baseline-alias local_rag \
  --candidate-alias local_rag_fast \
  --output-dir /tmp/openclaw_g2_alias_comparison
```

Multiple candidates can be passed by repeating `--candidate-alias`.

The script is guarded by `RUN_RAG_ALIAS_COMPARISON=1`. Without the guard it
exits before running any comparison.

## Alias Rules

- `local_rag` remains the baseline and default.
- Candidate aliases must be semantic LiteLLM aliases.
- Candidate aliases must exist in the local LiteLLM config passed by
  `--litellm-config`.
- Candidate aliases must use local Ollama config only.
- Candidate alias `api_base` values must be literal local URLs using
  `http://localhost:` or `http://127.0.0.1:`.
- Environment references such as `os.environ/OLLAMA_API_BASE` are rejected by
  this comparison script because they cannot be proven local at config-read
  time.
- Candidate aliases must not equal `local_rag`.
- Concrete model names such as values containing `/` or `:` are rejected.
- Remote provider prefixes such as `openai/`, `anthropic/`, `gemini/`,
  `azure/`, `openrouter/`, and `xai/` are rejected.
- If a candidate alias defines `model_info.experimental`, it must be `true`.

The report marks candidates as experimental. A successful result never promotes
an alias automatically.

## Question Set

The comparison uses the existing synthetic golden question registry:

```text
tests/golden/questions.yaml
```

The same fixture is run for baseline and every candidate. Reports store a
fixture hash and `question_id` only; they do not store question text.

Measured runs are ordered round-robin by question:

```text
question 1 -> local_rag
question 1 -> candidate A
question 1 -> candidate B
question 2 -> local_rag
...
```

Each alias receives one warmup call before measured runs. The warmup result is
discarded and recorded only as `warmup_discarded: true` in the summary.

## Report Schema

The JSONL report writes one safe row per question/alias:

- `question_id`
- `alias`
- `alias_role`
- `experimental`
- `run_type`
- `total_ms`
- `generation_ms`
- `prompt_eval_duration_ms`
- `eval_duration_ms`
- `eval_count`
- `tokens_per_second`
- `answer_length_chars`
- `citation_present`
- `fallback_applied`
- `estimated_remote_tokens_avoided`

The summary JSON includes:

- `baseline_alias`
- `candidate_aliases`
- `question_fixture_hash`
- `warmup_discarded`
- `default_unchanged`
- `results_by_alias`
- `delta_by_candidate`
- `citation_regression`
- `quality_regression`
- `hypothesis_supported`

Reports never include answer text, prompt text, chunks, vectors, Qdrant
payloads, headers, API keys, raw exceptions, tracebacks, or local paths.

## Interpretation

A candidate supports the G2-PR06 hypothesis only when:

- `total_ms` or `generation_ms` improves materially versus `local_rag`;
- `citation_regression` is `false`;
- no safety violation is present;
- the same question fixture and run type were used;
- `local_rag` remains unchanged as the default.

Promotion of a candidate alias requires a separate future PR and explicit human
approval.
