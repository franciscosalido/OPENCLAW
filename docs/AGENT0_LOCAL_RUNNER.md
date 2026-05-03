# Agent-0 Local Runner

Agent-0 is the first local MVP entrypoint for OpenClaw/Quimera.

It is a CLI only. It is not multi-agent orchestration, not a daemon, not an
API, not FastAPI and not MCP.

## Command

```bash
uv run python scripts/run_local_agent.py "Pergunta sintetica"
```

Flags:

- `--rag`: use the existing local RAG pipeline and `local_rag` generation.
- `--json`: use `local_json`.
- `--output text|json`: choose output format.
- `--show-metadata`: show safe metadata in text mode.
- `--max-tokens INT`: pass a local generation token cap where supported.
- `--temperature FLOAT`: pass local generation temperature where supported.
- `--dry-run`: route and estimate tokens without model calls.
- `--debug`: include exception class only in safe error category.

`--rag` and `--json` cannot be combined.

## Paths

Default:

```text
question -> decide_route -> local_chat -> answer
```

JSON:

```text
question -> decide_route -> local_json -> answer
```

RAG:

```text
question -> decide_route -> existing LocalRagPipeline/local_rag -> answer
```

RAG is explicit opt-in. GW-15 does not ingest documents, reindex, create
collections, delete collections or mutate Qdrant.

## Safe JSON Output

`--output json` returns only:

```json
{
  "answer": "...",
  "route": "local",
  "alias": "local_chat",
  "used_rag": false,
  "latency_ms": 1234.5,
  "decision_id": "...",
  "estimated_remote_tokens_avoided": 850
}
```

On failure it may also include `error_category`.

When GW-17 local fail-safe degradation applies, it may also include these safe
optional fields:

- `fallback_applied`
- `fallback_from_alias`
- `fallback_to_alias`
- `fallback_reason`
- `fallback_chain`
- `block_reason`

It never includes question text, prompts, chunks, vectors, embeddings, payloads,
API keys, Authorization headers, secrets, passwords, raw model responses or
tracebacks.

## GW-16 Contract Hardening

GW-16 freezes the Agent-0 runner contracts with offline tests only.

Alias matrix:

| Mode | Alias | `used_rag` |
|---|---|---:|
| default | `local_chat` | `false` |
| `--json` | `local_json` | `false` |
| `--rag` | `local_rag` | `true` |

Output schema invariants:

- `answer`, `route`, `alias`, `used_rag`, `latency_ms`, `decision_id`, and
  `estimated_remote_tokens_avoided` are always present.
- `error_category` appears only for blocked/failure results.
- `latency_ms` is numeric and non-negative.
- `estimated_remote_tokens_avoided` is numeric and non-negative.
- `decision_id` is non-empty.

Safe error categories:

- `blocked`
- `chat_unavailable`
- `json_unavailable`
- `rag_unavailable`
- `invalid_arguments` is reserved for future CLI/reporting integration.

GW-16 fallback remained intentionally disabled:

- RAG failure does not fallback to `local_chat`.
- JSON failure does not fallback to `local_chat`.
- Chat failure does not try another alias.
- Timeout/retry fallback is deferred to a future PR.

## GW-17 Local Fail-Safe Degradation

GW-17 adds one explicit local-only fallback path for recoverable local
infrastructure failure.

Fallback matrix:

| Condition | Behavior | Exit |
|---|---|---:|
| RAG/Qdrant unavailable | fallback once from `local_rag` to `local_chat` | `0` if fallback succeeds |
| fallback `local_chat` fails | safe failure, no second fallback | non-zero |
| `budget_exceeded` policy block | structured refusal, no model call, no fallback | non-zero |
| `unsupported_task` policy block | structured refusal, no model call, no fallback | non-zero |
| `local_think` timeout | deferred because Agent-0 has no public think path yet | n/a |
| JSON failure | safe failure, no fallback to chat | non-zero |
| Chat failure | safe failure, no fallback | non-zero |

Fallback reason codes are enum-derived and never free-form strings:

- `qdrant_unavailable`
- `rag_unavailable`
- `think_timeout`
- `alias_unavailable`
- `budget_exceeded`
- `unsupported_task`
- `fallback_alias_failed`
- `unknown_local_failure`

Successful fallback returns the fallback answer and preserves the stable output
schema. It sets `alias` to the alias that produced the answer, currently
`local_chat`, and sets `used_rag` to `false`.

Fallback emits a local loguru event named `agent_fallback` with only safe
metadata: decision id, enum reason, source alias, target alias, success flag,
latency and status. It does not log question text, prompts, answers, chunks,
vectors, payloads, exception messages, tracebacks, API keys or Authorization
headers.

## Dry Run

```bash
uv run python scripts/run_local_agent.py "Pergunta sintetica" --dry-run --output json
```

Dry-run needs no live LiteLLM, Ollama or Qdrant services.

## Optional Smoke

```bash
RUN_AGENT0_LOCAL_SMOKE=1 scripts/test_agent0_local_runner.sh
```

The smoke script is opt-in and local-only. It requires
`QUIMERA_LLM_API_KEY` to match the local `LITELLM_MASTER_KEY`.

## Gateway-1 Proof-of-Life

GW-20 adds the final Gateway-1 proof-of-life smoke:

```bash
RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run python scripts/test_gateway1_proof_of_life.py --output-dir /tmp/openclaw_gateway1_smoke
```

The command validates dry-run, local service probes, live `local_chat`, live
`--rag` success or explicit fallback, forced Qdrant degradation and policy block
behavior. It writes only sanitized metadata and answer lengths, never answer
text, prompt text, chunks, vectors, payloads or secrets.

## Deferred

- Progressive remote escalation remains out of scope.
- Golden questions harness is provided by GW-18 in
  `scripts/run_golden_harness.py`.
- Observability signal validation is covered by GW-19; Gateway-1 proof-of-life
  is covered by GW-20.
- Remote providers remain disabled and require a future ADR.
