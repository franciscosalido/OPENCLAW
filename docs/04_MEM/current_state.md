# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-04-30
**Updated by:** Codex — Gateway GW-07 synthetic RAG E2E

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

Current embedding path:

```text
RAG / OllamaEmbedder
  -> Ollama direct at http://127.0.0.1:11434/api/embed
```

GW-06 adds an experimental evaluation-only path:

```text
GatewayEmbedClient
  -> LiteLLM at http://127.0.0.1:4000/v1/embeddings
  -> Ollama / nomic-embed-text local
```

GW-07 proves the current RAG E2E path without migrating embeddings:

```text
synthetic docs
  -> chunking
  -> OllamaEmbedder direct at http://127.0.0.1:11434/api/embed
  -> Qdrant temporary collection gw07_synthetic_rag_<short_uuid>
  -> Retriever / ContextPacker / PromptBuilder
  -> LocalGenerator / GatewayChatClient
  -> LiteLLM at http://127.0.0.1:4000/v1/chat/completions
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
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Done / merged |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live smoke with effective timeout observability | Done / merged |
| GW-06 | `feat/gateway-local-embed-evaluation` | Evaluate embeddings via `local_embed` | Done / merged |
| GW06C | `feat/adr-openai-compatible-embeddings-contract` | OpenAI-compatible embeddings ADR and `quimera_embed` | Done / merged |
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | Current |

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>
GW-05b issue: <https://github.com/franciscosalido/OPENCLAW/issues/28>
GW-06 issue: <https://github.com/franciscosalido/OPENCLAW/issues/30>
GW-07 issue: <https://github.com/franciscosalido/OPENCLAW/issues/38>

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

- Add `timeout_s` to gateway call debug logs.
- Run expanded live smoke with LiteLLM and Ollama actually running when
  `RUN_LITELLM_SMOKE=1` is explicitly set.
- Validate `local_chat`, `local_think`, `local_rag`, and `local_json` against
  their effective timeout budgets.
- Keep smoke synthetic-only and local-only.
- Do not introduce remote providers, real data, RAG E2E, or embeddings through
  LiteLLM.

Live smoke status for GW-05b:

- **2026-04-28: PASSED** — Cenário A completo.
- 128/128 unit+integration tests passed. mypy 0. pyright 0.
- `RUN_LITELLM_SMOKE=1 pytest tests/smoke/` — 7/7 passed.
- `RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 pytest tests/smoke/` — 7/7 passed (54s).

Observed latencies (macOS, qwen3:14b Q4_K_M):

| Alias | elapsed_s | timeout_s |
|---|---:|---:|
| `local_chat` | 2.20 | 30.0 |
| `local_think` | 12.44 | 120.0 |
| `local_rag` | 2.23 | 60.0 |
| `local_json` | 1.72 | 30.0 |

GW-06:

- Evaluate whether embeddings should route through `local_embed`.
- Add an experimental `GatewayEmbedClient` for OpenAI-compatible
  `/embeddings` calls through LiteLLM.
- Keep existing direct/local embedding behavior as the default RAG path.
- Do not reindex Qdrant or touch real documents.
- Use only synthetic smoke inputs.
- Live evaluation on 2026-04-28 passed against local LiteLLM + Ollama.
- Decision status: **Approved for future migration**.
- Migration is still not performed in GW-06; a future PR must preserve or
  replace the current Ollama embedder's retry/backoff/concurrency behavior.

Observed local_embed results (2026-04-28):

| Check | Result |
|---|---|
| LiteLLM single embedding | 768 dimensions, 0.08s |
| LiteLLM batch embedding | 2 vectors, 768 dimensions each, 0.05s |
| Direct Ollama parity | 768 dimensions |
| Cosine similarity | 1.000000 |
| Script smoke | 768 dimensions, 0.70s |

GW-07:

- Prove a synthetic RAG end-to-end flow against the gateway path.
- Keep Qdrant data synthetic and local.
- Use a unique temporary collection named `gw07_synthetic_rag_<short_uuid>`.
- Attempt prefix-guarded cleanup and delete only temporary collections with the
  `gw07_synthetic_rag_` prefix.
- Never touch `openclaw_knowledge`.
- Keep embeddings direct through `OllamaEmbedder`; `quimera_embed` appears only
  as embedding contract metadata in this PR.
- Generate the final answer through LiteLLM using `local_rag`.
- Run only when explicitly enabled with `RUN_RAG_E2E_SMOKE=1`.

Manual live command:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

Direct pytest command:

```bash
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

Cleanup is attempted in teardown. If cleanup is interrupted, manually delete
only Qdrant collections whose names start with `gw07_synthetic_rag_`.

Live status:

- **2026-04-30: PASSED** — Cenário A completo for GW-07.
- Command: `RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v -s`.
- Corpus: 3 PT-BR synthetic documents, 14 chunks, 5 chunks retrieved/used.
- Temporary collection: `gw07_synthetic_rag_<short_uuid>` with prefix-guarded
  cleanup for the recorded run; interrupted runs may require manual cleanup by
  prefix.
- Embedding path: direct `OllamaEmbedder` to Ollama `/api/embed`.
- Generation path: `LocalGenerator` / `GatewayChatClient` through LiteLLM
  `local_rag`.

Observed GW-07 latencies (2026-04-30):

| Stage | Latency |
|---|---:|
| embedding/indexing | 178.1 ms |
| retrieval | 18.4 ms |
| generation | 3621.2 ms |
| total pipeline | 3639.6 ms |

---

## Validation Expectations For GW-07

Before opening PR:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_embed_client.py -v
uv run pytest tests/smoke/ -v
```

Live smoke tests should skip by default unless their explicit guards are set.
GW-07 requires `RUN_RAG_E2E_SMOKE=1`.

Optional live validation when local services are already running:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
scripts/test_local_embed_litellm.sh
```

Optional GW-07 live validation when Qdrant, Ollama, LiteLLM, and credentials are
already running locally:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```
