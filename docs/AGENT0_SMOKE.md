# Agent-0 Gateway-1 Proof-of-Life Smoke

GW-20 adds the final operational proof-of-life smoke for Sprint Gateway-1. It
is a single opt-in command that validates the local stack as a unit before
Gateway-2 starts.

## Command

```bash
RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run python scripts/test_gateway1_proof_of_life.py --output-dir /tmp/openclaw_gateway1_smoke
```

The command exits `0` only when every mandatory Gateway-1 done criterion passes.
It writes a sanitized JSON summary named:

```text
gateway1_proof_of_life_<run_id>.json
```

Generated reports under `reports/gateway1_smoke/` are ignored by Git.

## Prerequisites

The live portions require local services only:

- Ollama: `http://127.0.0.1:11434`
- Qdrant: `http://127.0.0.1:6333`
- LiteLLM: `http://127.0.0.1:4000/v1`

Required environment:

```bash
export QUIMERA_LLM_API_KEY="dev-local-key-change-me"
export QUIMERA_LLM_BASE_URL="http://127.0.0.1:4000/v1"
export QDRANT_URL="http://127.0.0.1:6333"
export OLLAMA_API_BASE="http://127.0.0.1:11434"
```

The script refuses non-local service URLs before any live probe.

## Done Criteria

The fixed criteria live in
`docs/sprints/GATEWAY1_DONE_CRITERIA.md`:

- G1-01 dry-run runner ok
- G1-02 local URLs only
- G1-03 Ollama probe ok
- G1-04 Qdrant probe ok
- G1-05 LiteLLM probe ok
- G1-06 local chat runner ok
- G1-07 RAG path or explicit fallback ok
- G1-08 forced Qdrant degradation ok
- G1-09 policy block no model call ok
- G1-10 sanitized output ok
- G1-11 summary report written ok

## Summary Shape

The summary contains only safe metadata:

- `run_id`
- `timestamp_utc`
- `gateway_sprint`
- `criteria_manifest_ref`
- `service_probes`
- `runner_tests`
- `passed`
- `failed`
- `skipped`
- `criteria_met`
- `overall_passed`

Runner results store answer length, alias, route, `used_rag`, fallback metadata
and token estimates. They do not store answer text.

## RAG Success vs Fallback

`G1-07` accepts either:

- RAG success through `local_rag` with `used_rag=true`; or
- explicit GW-17 fallback to `local_chat` with `used_rag=false` and an
  enum-derived fallback reason.

Both outcomes are valid because Gateway-1 requires honest local degradation, not
silent fallback or remote escalation.

## Forced Qdrant Degradation

`G1-08` injects a Qdrant-like unavailable error through the Agent-0 runner test
hook. It does not stop Docker, mutate Qdrant, delete collections, reindex, or
touch `openclaw_knowledge`.

## Safety

The proof-of-life summary and runtime checks never include:

- prompt, question or raw user input
- answer text
- chunks or retrieved context
- vectors or embeddings
- Qdrant payloads
- API keys, Authorization headers, tokens, passwords or secrets
- raw model responses
- raw exceptions, exception messages or tracebacks
- model weights paths

Remote providers remain disabled. Gateway-2 must not begin until GW-20 passes
locally.
