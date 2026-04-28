# Gateway Sprint Handoff

> Start each Gateway cycle by reading this file before touching Git.

**Last updated:** 2026-04-27
**Repository:** OpenClaw
**Product:** Quimera
**Sprint:** Gateway-0 / LiteLLM

---

## Mandatory GitHub Workflow

GitHub is the source of truth for issues, branches, pull requests, review state,
and merge state. The local checkout is a work area, not the final integration
point.

For every tracked PR:

1. Sync local `main`.
2. Open or update a GitHub Issue before implementation.
3. Create the feature branch from updated `main`.
4. Implement locally.
5. Run relevant validations locally.
6. Commit with clear atomic messages.
7. Push the feature branch.
8. Open a GitHub PR from the feature branch to `main`.
9. Link the PR to the issue.
10. Address review comments on the same branch.
11. Merge only in GitHub after approval.
12. After GitHub merge, sync local `main` with `--ff-only`.

Canonical start:

```bash
cd /Users/fas/projetos/OPENCLAW
git checkout main
git pull --ff-only origin main
```

Never push directly to `main`. Never use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Current Status

Current active branch:

```text
feat/gateway-per-alias-timeouts
```

Current issue:

```text
https://github.com/franciscosalido/OPENCLAW/issues/25
```

Gateway baseline already merged:

```text
GW-01 through GW-04 are merged in 92c0ec5.
```

Gateway PR state:

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | Gateway contracts, ADR, Blueprint, semantic aliases | Merged in `92c0ec5` |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM install and health scripts | Merged in `92c0ec5` |
| GW-03 | `feat/gateway-route-opencraw-litellm` | OpenClaw runtime chat through LiteLLM | Merged in `92c0ec5` |
| GW-04 | `feat/gateway-runtime-smoke` | Shared validation, optional smoke, observability | Merged in `92c0ec5` |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Current |
| GW-05b | TBD | Expanded live smoke with real local services | Planned |
| GW-06 | TBD | Evaluate embeddings via `local_embed` | Planned |
| GW-07 | TBD | Synthetic RAG E2E through gateway path | Planned |

---

## GW-05a Contract

Objective:

Add per-alias timeout configuration for semantic LiteLLM aliases without
changing the runtime architecture.

Timeout contract:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat |
| `local_think` | 120.0s | Longer reasoning/planning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured responses |
| `local_embed` | 30.0s | Placeholder only; not used for embeddings yet |

Resolution rules:

- If the request alias exists in `per_alias_timeouts`, use that timeout.
- If the alias is unknown, use global `timeout_seconds`.
- If the alias is `None`, use global `timeout_seconds`.
- Reject zero, negative, infinite, or NaN timeout values.

Out of scope:

- Live smoke expansion.
- FastAPI.
- MCP.
- Remote providers.
- Quant tools.
- Embeddings through LiteLLM.
- Qdrant/retrieval/chunking changes.
- Prompt builder changes.
- Autoprogramming.

---

## Next Work

GW-05b:

- Run expanded live smoke with LiteLLM and Ollama already running.
- Keep smoke opt-in with `RUN_LITELLM_SMOKE=1`.
- Use only synthetic prompts and local aliases.

GW-06:

- Evaluate whether `local_embed` should route embeddings through LiteLLM.
- Preserve current direct/local embedding path until the PR proves parity.

GW-07:

- Run synthetic RAG E2E over the approved gateway path.
- Keep all data fictitious and local.

---

## Validation Checklist

Before opening GW-05a PR:

```bash
git status --short --branch
git diff --stat
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_config.py -v
uv run pytest tests/unit/test_gateway_client.py -v
uv run pytest tests/smoke/ -v
```

Expected smoke behavior without `RUN_LITELLM_SMOKE=1`: smoke tests skip, not
fail.
