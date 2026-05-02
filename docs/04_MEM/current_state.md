# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-05-01
<<<<<<< HEAD
**Updated by:** Codex — Gateway GW-14 routing audit and token economy
=======
**Updated by:** Codex — Agent-0 GW-15 local runner
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

---

## Active Sprint: Agent-0 / Local Runner MVP

<<<<<<< HEAD
**Goal:** add safe, offline local-first routing decision primitives and token
economy records for future routing policy work. Remote providers remain
disabled and no runtime model routing changes are made in Gateway-1 policy
work.

Gateway-0 is complete on `main`. Gateway-1 started from issue
[#51](https://github.com/franciscosalido/OPENCLAW/issues/51). GW-14 continues
from issue [#53](https://github.com/franciscosalido/OPENCLAW/issues/53) on
branch `feat/gateway1-routing-audit-token-economy`.
=======
**Goal:** add the first local MVP CLI entrypoint for one question, one routing
decision, one local-only execution path and safe metadata output.

Gateway-0 is complete on `main`. GW-13 is merged. GW-14 remains a separate
open PR at the time GW-15 starts, so GW-15 uses compatibility helpers when the
GW-14 token/config helpers are not present on `main`.

GW-15 issue: <https://github.com/franciscosalido/OPENCLAW/issues/55>
GW-15 branch: `feat/agent0-local-runner`
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

Current runtime path:

```text
OpenClaw / runtime generation
  -> LiteLLM at http://127.0.0.1:4000/v1
  -> Ollama / Qwen local
```

Current controlled embedding path:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM at http://127.0.0.1:4000/v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text local
```

Rollback embedding path:

```text
RagEmbedder factory
  -> direct_ollama
  -> OllamaEmbedder
  -> Ollama direct at http://127.0.0.1:11434/api/embed
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
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | Done / merged |
| GW-08 | `feat/rag-controlled-embedding-migration` | Controlled RAG embedding migration to `quimera_embed` | Done / merged |
| GW-09 | `feat/rag-collection-metadata-guard` | Collection metadata drift guard for embedding traceability | Done / merged |
| GW-10 | `feat/rag-run-trace-provenance` | Safe per-query RAG provenance trace | Done / merged |
| GW-11 | `feat/rag-observability-events` | Safe structured RAG lifecycle observability events | Done / merged |
| GW-12 | `feat/gateway-operational-readiness` | Final runbook, readiness checks, ADR boundary, handoff | Done / merged |
| GW-13 | `feat/gateway1-routing-policy-prelude` | Gateway-1 local-first routing policy and token economy prelude | Done / merged |
<<<<<<< HEAD
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Current |
=======
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Open / separate PR |
| GW-15 | `feat/agent0-local-runner` | Agent-0 local CLI runner MVP | Current |
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>
GW-05b issue: <https://github.com/franciscosalido/OPENCLAW/issues/28>
GW-06 issue: <https://github.com/franciscosalido/OPENCLAW/issues/30>
GW-07 issue: <https://github.com/franciscosalido/OPENCLAW/issues/38>
GW-08 issue: <https://github.com/franciscosalido/OPENCLAW/issues/40>
GW-09 issue: <https://github.com/franciscosalido/OPENCLAW/issues/42>
GW-10 issue: <https://github.com/franciscosalido/OPENCLAW/issues/44>
GW-11 issue: <https://github.com/franciscosalido/OPENCLAW/issues/46>
GW-12 issue: <https://github.com/franciscosalido/OPENCLAW/issues/48>
GW-13 issue: <https://github.com/franciscosalido/OPENCLAW/issues/51>
<<<<<<< HEAD
GW-14 issue: <https://github.com/franciscosalido/OPENCLAW/issues/53>
=======
GW-15 issue: <https://github.com/franciscosalido/OPENCLAW/issues/55>
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

Gateway-0 sprint complete. GW-01 through GW-12 merged on `main`.
The next sprint must start from a new explicit issue, ADR if architecture
changes, and `git pull --ff-only origin main`.

<<<<<<< HEAD
=======
## GW-15 Current Work

GW-15 creates Agent-0, the first local MVP runner:

```text
question
  -> decide_route(...)
  -> local_chat | local_json | explicit local_rag
  -> safe answer metadata
```

Deliverables:

- `scripts/run_local_agent.py`.
- `scripts/test_agent0_local_runner.sh` optional smoke guarded by
  `RUN_AGENT0_LOCAL_SMOKE=1`.
- `docs/AGENT0_LOCAL_RUNNER.md`.
- `tests/unit/test_run_local_agent.py`.

Rules:

- Default execution uses `local_chat`.
- `--json` uses `local_json`.
- `--rag` explicitly opts into the existing local RAG path and `local_rag`.
- `--dry-run` works without live services.
- No remote providers, no remote calls, no API keys, no FastAPI, no MCP.
- No Qdrant mutation, no reindexing, no ingestion, no real data.
- Progressive fallback is deferred to GW-16.
- Golden questions harness is deferred to GW-17.

>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)
## GW-13 Completed Work

GW-13 opens Gateway-1 with safe routing policy records only.

Deliverables:

- `backend/gateway/routing_policy.py` with frozen decision and token economy
  dataclasses.
- `config/rag_config.yaml` `gateway.routing` defaults with
  `remote_enabled: false` and no allowed remote providers.
- `docs/GATEWAY1_ROUTING_POLICY.md`.
- `docs/ADR/0020-controlled-remote-escalation-policy.md` with status Proposed.
- `docs/sprints/GATEWAY1_SPRINT_HANDOFF.md`.
- `tests/unit/test_gateway_routing_policy.py`.

Rules:

- No remote providers.
- No remote calls.
- No API keys.
- No runtime model routing change.
- No Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge` access.
- Token economy is estimated only, not billed.
- Remote escalation requires future sanitization and an explicit Accepted ADR.

## GW-14 Current Work

GW-14 connects Gateway-1 routing primitives to config and local audit records.

Deliverables:

- `load_routing_policy()` reads `gateway.routing` from `config/rag_config.yaml`.
- `estimate_prompt_tokens()` adds heuristic token estimation without a
  tokenizer dependency.
- `TokenBudgetAccumulator` tracks session-local estimates in memory only.
- `RoutingDecisionLogger` writes safe append-only JSONL audit records under
  `logs/`.
- `RouterDecision.decision_fingerprint()` hashes safe policy-relevant fields.
- Task type blocking/allowing is config-driven.

Rules:

- `remote_enabled` remains false.
- `allowed_remote_providers` remains empty.
- No remote calls, no remote provider API keys, no runtime routing change.
- JSONL audit files are local artifacts and must not be committed.
- Local fallback on timeout and health-aware routing are deferred.

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

## GW-12 Completed Work

GW-12 closed Gateway-0 as an operational readiness PR, not a feature PR.

Deliverables:

- `docs/GATEWAY_FINAL_RUNBOOK.md`.
- `scripts/check_gateway_readiness.sh` with static default mode and explicit
  `--live`.
- `tests/unit/test_gateway_readiness_script.py`.
- `tests/unit/test_gateway_final_baseline.py`.
- `docs/ADR/0019-gateway-0-sprint-boundary.md`.
- Final updates to shared context, setup, runtime and handoff docs.

Rules respected:

- No runtime architecture change.
- No remote providers.
- No FastAPI, MCP, quant tools, OpenTelemetry, Prometheus, Grafana,
  dashboards, profiling, or mandatory soak tests.
- No Qdrant mutation, no reindexing, no `openclaw_knowledge` access.
- Live proof remains opt-in and must not become CI.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## Historical Work

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

## GW-10 Completed Work

GW-10 adds `RagRunTrace`, a safe frozen dataclass for per-query provenance:

```text
LocalRagPipeline.ask(...)
  -> retrieval/prompt/generation timings
  -> RagRunTrace safe metadata only
  -> logger.bind(trace=...).log(...)
```

Trace scope:

- Records collection name, embedding backend/model/alias/dimensions, chunk
  count, gateway alias, and latency metadata.
- Does not record query text, chunk text, prompts, answer text, vectors,
  payloads, real portfolio data, private documents, API keys, Authorization
  headers, or secrets.
- Uses `rag.tracing.enabled` and `rag.tracing.log_level` from
  `config/rag_config.yaml`.
- Raises `EmbeddingDimensionMismatchError` if trace dimensions diverge from
  active expected dimensions.
- Does not mutate Qdrant, reindex collections, or touch `openclaw_knowledge`.

GW-11 current work remains separate from `RagRunTrace`: lifecycle events are
local structured loguru records around embedding, retrieval, and generation.
Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

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

## GW-08 Completed Work

GW-08 aligns new controlled RAG embedding generation with the accepted
OpenAI-compatible embeddings contract:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text
```

Rollback remains explicit:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

Key rules:

- `OllamaEmbedder` remains available.
- `direct_ollama` remains the rollback backend.
- Existing collections are not reindexed automatically.
- `openclaw_knowledge` is not touched.
- Vectors from different embedding backends, models, providers, or dimensions
  must not be mixed silently in one collection.
- GW-08 smoke uses temporary collections with prefix
  `gw08_embedding_migration_`.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

Optional live validation:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_gw08_embedding_migration.sh
```

Live status:

- **2026-04-30: PASSED** — controlled migration smoke and parity smoke passed.
- Required operational note: restart LiteLLM after adding `quimera_embed`; an
  old LiteLLM process may still expose only `local_embed`.
- Command: `QUIMERA_LLM_API_KEY=<local-placeholder> scripts/test_gw08_embedding_migration.sh`.
- Temporary collection prefix: `gw08_embedding_migration_`.
- Synthetic chunks: 4 indexed, 4 retrieved/used.
- Embedding path: `RagEmbedder factory -> gateway_litellm -> GatewayEmbedClient -> LiteLLM /v1/embeddings -> quimera_embed`.
- Generation path: `LocalGenerator / GatewayChatClient -> LiteLLM local_rag`.
- Rollback path remains: `QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama`.
- `openclaw_knowledge` was not touched.

Observed GW-08 latencies and parity (2026-04-30):

| Check | Result |
|---|---:|
| embedding/indexing | 314.7 ms |
| retrieval | 27.4 ms |
| generation | 4951.7 ms |
| total pipeline | 4979.1 ms |
| cosine similarity vs direct Ollama | 1.000000 |
| vector dimensions | 768 |

## GW-09 Completed Work

GW-09 adds a traceability guard for Qdrant collection embedding metadata:

```text
Qdrant payload sample
  -> embedding_backend/model/dimensions/contract/alias check
  -> structured warning on drift
  -> hard error only for dimension mismatch by default
```

Key rules:

- The guard samples payloads with `with_payload=True` and `with_vectors=False`.
- It does not mutate, delete, recreate, or reindex collections.
- It does not touch `openclaw_knowledge`.
- Backend, model, contract, alias, and missing metadata drift warn by default.
- Dimension mismatch always raises `EmbeddingDimensionMismatchError`.
- `strict=True` can raise on backend/model/contract/alias mismatch.
- No chunk text, vectors, prompts, secrets, or Authorization headers are logged.
- GW-10 remains the place for `RagRunTrace`.
- GW-11 adds structured RAG observability lifecycle events separately.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

## GW-11 Completed Work

GW-11 adds local structured RAG lifecycle observability events:

```text
embedding/retrieval/generation stage
  -> RagObservabilityEvent safe metadata only
  -> logger.bind(event=...).log(...)
```

Scope:

- `backend/rag/observability.py` defines event kinds, error categories, config,
  safe serialization, emission, and exception categorization.
- `GatewayEmbedClient` emits embedding started/finished/failed events for
  `gateway_litellm`.
- `OllamaEmbedder` emits embedding started/finished/failed events for
  `direct_ollama`.
- `LocalRagPipeline` emits retrieval and generation lifecycle events.
- `config/rag_config.yaml` has `rag.observability` flags and log level.

Safety rules:

- Events contain only safe scalar metadata.
- Events never include query text, prompt text, answer text, chunk text,
  document text, vectors, Qdrant payloads, portfolio data, API keys,
  Authorization headers, tokens, passwords, or secrets.
- No return values change.
- Retry/backoff/concurrency semantics are unchanged.
- Qdrant is not mutated and `openclaw_knowledge` is not touched.

Out of scope:

- OpenTelemetry, Prometheus, Grafana, dashboards, distributed tracing,
  profiling, soak tests, and memory/resource baselines.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.
