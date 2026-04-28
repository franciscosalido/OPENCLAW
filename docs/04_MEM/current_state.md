# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-04-27
**Updated by:** Codex — Gateway GW-05a per-alias timeout prep

---

## Active Sprint: Gateway-0 / LiteLLM

**Goal:** make LiteLLM the local-only model gateway for OpenClaw runtime model
calls while preserving existing RAG/Qdrant behavior.

Current runtime path:

```text
OpenClaw / runtime generation
  -> LiteLLM at http://127.0.0.1:4000/v1
  -> Ollama / Qwen local
```

Hard constraints remain:

- Local only.
- No remote providers.
- No FastAPI.
- No MCP.
- No quant tools.
- No secrets or real portfolio data.
- No final local merge into `main`; GitHub PR approval is the integration path.

---

## Mandatory GitHub Workflow

For every tracked task:

1. Sync local `main` with GitHub.
2. Open or update a GitHub Issue before implementation.
3. Create a feature branch from updated `main`.
4. Implement locally.
5. Run validation locally.
6. Commit atomic changes.
7. Push the feature branch.
8. Open a GitHub PR to `main`.
9. Link the PR to the issue.
10. Address review on the same branch.
11. Merge only in GitHub after approval.
12. After merge, pull `main` with `--ff-only` and delete branches only when safe.

Do not push directly to `main`. Do not use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Gateway PR Tracking

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | ADR, Blueprint V3.0, semantic aliases, config contracts | Done / merged |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM operational setup | Done / merged |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Runtime chat/generation through LiteLLM | Done / merged |
| GW-04 | `feat/gateway-runtime-smoke` | Shared message validation, optional smoke, observability | Done / merged |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Current |
| GW-05b | TBD | Expanded live smoke with real local services | Planned |
| GW-06 | TBD | Evaluate embeddings via `local_embed` | Planned |
| GW-07 | TBD | Synthetic RAG E2E through gateway path | Planned |

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>

---

## GW-05a Timeout Contract

Runtime gateway calls now reserve different timeout budgets per semantic alias:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat calls |
| `local_think` | 120.0s | Longer local reasoning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured local responses |
| `local_embed` | 30.0s | Placeholder only; embeddings are not routed through LiteLLM in GW-05a |

Unknown aliases and `None` fall back to the global `timeout_seconds`.

---

## Next Planned Work

GW-05b:

- Run expanded live smoke with LiteLLM and Ollama actually running.
- Keep smoke opt-in and synthetic-only.
- Do not introduce remote providers or real data.

GW-06:

- Evaluate whether embeddings should route through `local_embed`.
- Keep existing direct/local embedding behavior until a tested PR changes it.

GW-07:

- Prove a synthetic RAG end-to-end flow against the gateway path.
- Keep Qdrant data synthetic and local.

---

## Validation Expectations For GW-05a

Before opening PR:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_config.py -v
uv run pytest tests/unit/test_gateway_client.py -v
uv run pytest tests/smoke/ -v
```

Smoke tests should skip by default unless `RUN_LITELLM_SMOKE=1` is set.
