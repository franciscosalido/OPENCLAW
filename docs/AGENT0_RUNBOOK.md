# Agent-0 Runbook

## Purpose

Agent-0 exposes the first public OpenClaw question interface:

```python
class OpenClaw:
    def ask(self, question: str) -> Answer: ...
```

The CLI wrapper is:

```bash
uv run python scripts/openclaw.py ask "qual o estado do GW-07?"
uv run python scripts/openclaw.py ask "qual o estado do GW-07?" --json
```

## Prerequisites

- Python 3.12 via `uv`.
- Local Qdrant reachable on localhost.
- LiteLLM local gateway reachable on `http://127.0.0.1:4000/v1`.
- Ollama has `qwen3:14b` and `nomic-embed-text`.
- A0-PR02 corpora have already been bootstrapped into:
  - `openclaw_internal`
  - `openclaw_financial`

Agent-0 readiness does not bootstrap, ingest, reindex or mutate Qdrant.

## Readiness

```bash
uv run python scripts/check_agent0_readiness.py --json
```

The readiness report is sanitized and checks:

- Qdrant collections exist.
- LiteLLM config has required aliases.
- Ollama models are available.
- Remote routing remains disabled.
- Golden questions and corpus manifests load.

## E2E SLOs

The live E2E suite is opt-in:

```bash
RUN_AGENT0_E2E=1 uv run pytest tests/e2e/test_agent0_e2e.py -v
```

Final SLOs:

- E2E p95 latency `< 15s`.
- `citation_present >= 5/6` on golden questions.
- zero remote provider imports in public Agent-0 modules.
- zero forbidden content keys in reports/log-like outputs.
- no regression in existing tests.

## Safe Output

`Answer.to_dict()` and E2E/readiness reports never include prompt, chunks,
chunk text, vectors, embeddings, payloads, headers, API keys, authorization,
raw exceptions or tracebacks.

## Rollback

See `docs/AGENT0_ROLLBACK.md`.

Never delete `openclaw_knowledge` during Agent-0 rollback.
