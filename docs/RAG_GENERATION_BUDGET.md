# RAG Generation Budget

G2-03 adds an optional local-only generation budget for `local_rag`.

This is a reversible performance experiment aimed at the `generation_ms`
segment. It does not change retrieval, `top_k`, context packing, Qdrant,
embeddings, model aliases, timeout values, `local_chat`, `local_json`, or the
Agent-0 fallback chain.

## Configuration

The budget is controlled by `config/rag_config.yaml`:

```yaml
rag:
  generation_budget:
    enabled: false
    apply_to_aliases:
      - "local_rag"
    max_tokens: 768
    enforce_conciseness: false
    target_sentences_min: 3
    target_sentences_max: 6
```

Rollback is a config-only change:

```yaml
rag:
  generation_budget:
    enabled: false
```

Additional rollback levers:

- `max_tokens: null` disables forwarding a generation cap.
- `enforce_conciseness: false` disables prompt discipline.

With `enabled: false`, the pre-G2-03 generation path is preserved.

## Scope

The budget applies only when the active generation alias is `local_rag` and the
alias is listed in `apply_to_aliases`.

It does not apply to:

- `local_chat`
- `local_json`
- `local_think`
- embedding calls

G2-03 intentionally keeps JSON mode and default chat behavior unchanged.

## Thinking Mode Warning

G2-03 validates `generation_budget` for `local_rag` with
`thinking_mode=false`. The combination of `generation_budget` and
`thinking_mode=True` is untested.

For Qwen3 thinking runs, reasoning tokens may consume the same
`max_tokens` / `num_predict` budget before final answer tokens are produced.
With a cap such as 768 tokens, this can truncate reasoning or leave little to
no useful final answer.

Do not enable `generation_budget` for thinking aliases until a dedicated
benchmark validates that path. `local_rag` should remain `think=false` for this
optimization.

## Max Tokens

When enabled and `max_tokens` is set, `LocalRagPipeline` forwards the cap to the
existing local generation path. `GatewayChatClient` includes `max_tokens` in the
OpenAI-compatible chat payload only when the value is provided.

When no per-call cap is provided, `LocalGenerator` keeps its existing default
budget behavior.

## Conciseness Discipline

When `enforce_conciseness` is true, `PromptBuilder` adds one modular instruction
to the RAG user prompt:

- answer in a concise sentence range;
- preserve the most important evidence;
- keep inline citations when context is available;
- avoid repeating retrieved passages verbatim;
- state insufficient context clearly.

The base system prompt is not rewritten. Citation format remains
`[doc_id#chunk_index]`.

## Trace Fields

`RagRunTrace` records safe scalar metadata:

- `answer_length_chars`
- `answer_token_estimate`
- `generation_budget_enabled`
- `generation_budget_applied`
- `generation_budget_max_tokens`
- `conciseness_instruction_applied`

The trace never stores answer text, prompt text, chunks, vectors, Qdrant
payloads, API keys, Authorization headers, raw exceptions, or tracebacks.

`answer_token_estimate` uses the same heuristic token estimator used by Gateway
routing. It is an estimate, not billing.

## Validation

Offline validation should prove:

- default config is rollback-safe;
- `max_tokens` is forwarded only for `local_rag` when enabled;
- `local_chat` and `local_json` are not affected;
- the conciseness instruction is omitted unless enabled;
- citation and insufficient-context instructions remain present;
- trace fields serialize through an allowlist without answer text;
- `local_rag` keeps `think: false` in the operational LiteLLM config;
- smoke tests remain opt-in.

Optional live validation can compare uncapped and capped `local_rag` runs with
the same synthetic question, checking:

- `generation_ms`;
- `eval_count` if available;
- `eval_duration_ms` if available;
- `answer_length_chars`;
- `answer_token_estimate`;
- citation presence;
- `total_ms`.

Do not commit generated reports.
