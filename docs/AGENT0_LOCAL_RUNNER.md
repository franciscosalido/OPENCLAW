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

Fallback remains intentionally disabled:

- RAG failure does not fallback to `local_chat`.
- JSON failure does not fallback to `local_chat`.
- Chat failure does not try another alias.
- Timeout/retry fallback is deferred to a future PR.

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

## Deferred

- Progressive fallback is deferred to GW-17.
- Golden questions harness is deferred to GW-18.
- Observability E2E validation is deferred to GW-18.
- Remote providers remain disabled and require a future ADR.
