# AGENT_CONTEXT.md — Shared Context for Codex + Claude

> Principal memory handoff file for Quimera/OpenClaw agents.
> Read this before implementation work. Update it at the end of every meaningful session.

**Project:** Quimera  
**Repository:** OpenClaw  
**Purpose:** local-first, security-first, multi-agent assistant  
**Scope:** operational context shared by Codex, Claude Code, ChatGPT Thinking, and human reviewers  
**Status:** active shared memory  

---

## 0. Rule Number One — Token Economy

These 15 rules are mandatory before any deep repo exploration or implementation:

1. Start with `git status`, not a full repository read.
2. Read first: `CLAUDE.md`, `AGENTS.md`, `README.md`, and `docs/04_MEM/current_state.md` when present.
3. Use targeted `rg`/`grep` before opening large files.
4. Ask for or produce a plan before editing.
5. Work one issue per session.
6. Use `/clear` between unrelated tasks in Claude Code.
7. Use `/compact` after long blocks, with explicit handoff instructions.
8. Use `/cost` to monitor token consumption.
9. Use `/memory` or this file for persistent context instead of repeating context in every chat.
10. Do not paste giant logs; summarize and include only the failing excerpt.
11. Keep PRs small.
12. Always create a handoff at session end.
13. Do not open `node_modules`, `.venv`, `dist`, caches, generated files, or large files unless explicitly needed.
14. Keep useful commands in project docs so agents do not rediscover them.
15. Record decisions in `docs/04_MEM/decisions.md` and live state in `docs/04_MEM/current_state.md`; do not depend on chat history.

---

## 1. A2A Coordination Protocol

This repository uses a lightweight Agent-to-Agent protocol.

### Roles

| Agent | Responsibility | Should Not Do |
|---|---|---|
| Human | Owns architecture, priorities, merge decisions | Delegate secrets or real portfolio data |
| ChatGPT Thinking | Architecture, critique, planning, tradeoffs | Commit code directly |
| Codex | Small implementation PRs, tests, validation, GitHub workflow | Change architecture without instruction |
| Claude Code | Implementation/review inside local workflow | Touch forbidden files without authorization |
| Cowork/Reviewer | Review diffs, run tests, reject unsafe changes | Expand scope silently |

### Message Contract

Every implementation session should produce:

1. Task restatement.
2. Risk level: low, medium, or high.
3. Files expected to change.
4. Validation plan.
5. Confirmation request when medium/high risk or when architecture, dependencies, secrets, data, or runtime services are affected.

Every handoff should include:

1. Branch and issue/PR links.
2. Files changed.
3. Commands run.
4. Test results.
5. What was intentionally not changed.
6. Remaining risks and next action.

---

## 2. Safety Boundaries

### Forbidden Unless Explicitly Authorized

- `CLAUDE.md`
- `.claude/`
- `.env`
- `.env.*`
- Secrets files
- Real portfolio data
- Real brokerage/account data
- Production databases
- Exported financial data
- Private documents outside the requested synthetic/test scope

### Project Security Levels

| Level | Meaning | Remote Use |
|---|---|---|
| Level 0 | Local-only data: private docs, positions, balances, logs, credentials, personal data | Never |
| Level 1 | Sanitized abstractions, anonymized errors, synthetic examples | Only after explicit sanitization |
| Level 2 | Public docs, toy examples, generic code structure | Safe |

RAG-0 is **local only**. No remote AI fallback in this sprint.

---

## 3. Current Architectural Assumptions

- Product name: Quimera.
- Repository name: OpenClaw.
- Model gateway: LiteLLM at `http://127.0.0.1:4000/v1` (Gateway-0 — local only).
- Semantic aliases: `local_chat`, `local_think`, `local_rag`, `local_json`, `quimera_embed`, `local_embed`.
- Local LLM runtime: Ollama through LiteLLM for chat and controlled gateway embeddings.
- Primary local generation model: `qwen3:14b` (vendor name confined to LiteLLM config — application code uses aliases).
- Embedding model: `nomic-embed-text`; application-facing alias is `quimera_embed`, with `direct_ollama` rollback retained.
- Vector database: Qdrant.
- Mathematical co-processor: deterministic Python modules.
- Remote AI: disabled. Sanitized fallback only after explicit sprint approval.
- GitHub is the source of truth for issues, branches, PRs, and merge state.

Runtime env vars (must be set locally before running OpenClaw):

| Var | Default | Notes |
|---|---|---|
| `QUIMERA_LLM_BASE_URL` | `http://127.0.0.1:4000/v1` | Local LiteLLM only |
| `QUIMERA_LLM_API_KEY` | — | Must match `LITELLM_MASTER_KEY` |
| `QUIMERA_LLM_MODEL` | `local_chat` | Semantic alias |
| `QUIMERA_LLM_REASONING_MODEL` | `local_think` | Semantic alias |
| `QUIMERA_LLM_RAG_MODEL` | `local_rag` | Semantic alias |
| `QUIMERA_LLM_JSON_MODEL` | `local_json` | Semantic alias |
| `QUIMERA_LLM_EMBED_MODEL` | `quimera_embed` | Canonical embedding alias |
| `QUIMERA_RAG_EMBEDDING_BACKEND` | `gateway_litellm` | Use `direct_ollama` for rollback |

Gateway-1 routing policy defaults:

| Field | Default | Notes |
|---|---|---|
| `gateway.routing.remote_enabled` | `false` | No remote calls allowed |
| `gateway.routing.default_route` | `local` | Local-first baseline |
| `gateway.routing.allowed_remote_providers` | `[]` | Empty until future ADR |
| `gateway.routing.per_request_token_limit` | `0` | No budget gate enforced yet |
| `gateway.routing.decision_log_path` | `logs/routing_decisions` | Local JSONL audit base path |
| `gateway.routing.blocked_task_types` | `trade_execution`, `brokerage_login` | Config-driven local blocks |

---

## 4. Sprint History and Current State

### Sprint RAG-0 — COMPLETE ✅

Canonical pipeline:

```text
SyntheticDocument
  -> Chunker
  -> Ollama Embeddings (direct)
  -> Qdrant VectorStore
  -> Retriever
  -> ContextPacker
  -> PromptBuilder
  -> LocalGenerator  ← now routes through LiteLLM gateway
  -> AnswerWithCitations
```

| PR | Branch | Scope | Status |
|---|---|---|---|
| RAG-01 | `feat/rag-chunking-*` | Chunking + tests | ✅ Merged |
| RAG-02 | `feat/rag-embeddings` | Ollama embeddings + tests | ✅ Merged |
| RAG-03 | `feat/rag-qdrant-store` | Qdrant store + integration tests | ✅ Merged |
| RAG-04 | `feat/rag-retriever-context` | Retriever + ContextPacker | ✅ Merged |
| RAG-05 | `feat/rag-local-pipeline-smoke` | PromptBuilder + LocalGenerator + fake smoke | ✅ Merged |
| RAG-06 | `feat/rag-cli-smoke` | Synthetic ingest/query CLI + preflight + smoke | ✅ Merged |
| RAG-07 | `feat/rag-docs-runbook` | Runbook + ADR + shared validation + health tests | ✅ Merged |

### Sprint Gateway-0 — COMPLETE ✅

Runtime path base merged to `main`:

```text
OpenClaw / LocalGenerator
  -> GatewayChatClient
  -> http://127.0.0.1:4000/v1 (LiteLLM)
  -> Ollama / Qwen local
```

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | Contracts, ADR, aliases | ✅ Merged |
| GW-02 | `feat/gateway-install-health` | Local LiteLLM operational setup | ✅ Merged |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Runtime chat/generation through LiteLLM | ✅ Merged |
| GW-04 | `feat/gateway-runtime-smoke` | Shared validation, optional smoke | ✅ Merged |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout contracts | ✅ Merged |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live gateway smoke with timeout observability | ✅ Merged |
| GW-06 | `feat/gateway-local-embed-evaluation` | `local_embed` evaluation | ✅ Merged |
| GW06C | `feat/adr-openai-compatible-embeddings-contract` | `quimera_embed` ADR contract | ✅ Merged |
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | ✅ Merged |
| GW-08 | `feat/rag-controlled-embedding-migration` | Controlled embedding migration to `quimera_embed` | ✅ Merged |
| GW-09 | `feat/rag-collection-metadata-guard` | Collection metadata drift guard | ✅ Merged |
| GW-10 | `feat/rag-run-trace-provenance` | `RagRunTrace` provenance | ✅ Merged |
| GW-11 | `feat/rag-observability-events` | Local structured RAG lifecycle events | ✅ Merged |
| GW-12 | `feat/gateway-operational-readiness` | Final runbook, readiness checks, ADR boundary | ✅ Merged |

### Sprint Gateway-1 — CURRENT

Gateway-1 starts after Gateway-0 readiness. GW-13 adds routing policy
primitives only:

```text
task metadata + token estimates
  -> local-first routing policy
  -> RouterDecision / TokenEconomyRecord
  -> no remote call
```

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-13 | `feat/gateway1-routing-policy-prelude` | Local-first routing decision records and token economy prelude | ✅ Merged |
<<<<<<< HEAD
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | 🚧 Current |
=======
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Open / separate PR |
| GW-15 | `feat/agent0-local-runner` | Agent-0 local CLI runner MVP | 🚧 Current |
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

GW-13 rules:

- Remote providers remain disabled.
- Remote candidates are metadata only, not execution.
- No secrets, no API keys, no remote calls.
- No runtime model routing change.
- No Qdrant mutation or `openclaw_knowledge` access.

<<<<<<< HEAD
GW-14 rules:

- Config-driven routing audit and token economy calibration.
- Local JSONL audit records, heuristic token estimation, in-memory token budget accumulation.
- Policy artifacts only — not billing, not runtime routing.
- `remote_enabled` remains false. `allowed_remote_providers` remains empty.
- No remote calls, no runtime routing change, no Qdrant mutation.
=======
GW-15 rules:

- `scripts/run_local_agent.py` is a local CLI, not an API, daemon,
  multi-agent system, FastAPI app or MCP server.
- Default mode uses `local_chat`.
- `--json` uses `local_json`.
- `--rag` is explicit opt-in and uses the existing RAG path when available.
- `--dry-run` must work without live services.
- Output metadata must not include question, prompt, chunks, vectors, payloads,
  raw responses, secrets or Authorization headers.
- Progressive fallback is deferred to GW-16.
- Golden questions harness is deferred to GW-17.
>>>>>>> 8a17f34 (feat(agent): add Agent-0 local runner)

**Gateway-0 final baseline:** local-only LiteLLM gateway, Qdrant vector store,
`quimera_embed` canonical embedding alias, `RagRunTrace` provenance,
`RagObservabilityEvent` lifecycle logs, and `scripts/check_gateway_readiness.sh`.

**Out of scope after Gateway-0:** remote providers, FastAPI, MCP, quant tools,
OpenTelemetry, profiling, dashboards, production ingestion and
`openclaw_knowledge` mutation. Each requires a new issue and explicit future
ADR/sprint.

Before starting a new PR:

```bash
git status --short --branch
git fetch --prune
gh pr list -R franciscosalido/OPENCLAW --state open
gh issue list -R franciscosalido/OPENCLAW --state open
```

---

## 5. Required Start Sequence

Agents should start sessions with the smallest useful context:

```bash
git status --short --branch
git fetch --prune
git branch -vv
rg --files docs/04_MEM backend/rag tests config docker | sort
```

Then read only what the task needs:

```bash
sed -n '1,220p' docs/04_MEM/AGENT_CONTEXT.md
sed -n '1,220p' docs/04_MEM/current_state.md
sed -n '1,220p' docs/04_MEM/decisions.md
```

Do not read `.env`, `.env.*`, `.claude/`, or large generated directories.

---

## 6. Branch and PR Discipline

- Use one branch per issue.
- GitHub is the source of truth for issue, branch, PR, review, and merge state.
- Start every tracked task by syncing `main` with GitHub:

```bash
cd /Users/fas/projetos/OPENCLAW
git checkout main
git pull --ff-only origin main
```

- Open or update a GitHub Issue before implementation.
- Create the feature branch only after `main` is updated.
- Keep diffs small enough to review in one pass.
- Commit locally, push the feature branch, and open a GitHub PR before review.
- Do not push directly to `main`.
- Do not merge locally into `main` as the final integration step.
- Final merge happens in GitHub after approval.
- After GitHub merge, sync local `main` with `git pull --ff-only origin main`.
- If a branch depends on an open PR, say so before implementing.

Recommended branch shape:

```text
feat/rag-<small-scope>
docs/<small-scope>
fix/<small-scope>
```

Required deliverables per tracked PR:

1. Issue title and issue description.
2. Branch name.
3. PR title and PR description.
4. Validation commands and results.
5. Merge readiness status.

---

## 7. Runtime Discipline

Local services must stay local:

| Service | Expected Use |
|---|---|
| Ollama | Local generation and embeddings |
| Qwen 3 14B | Thinking/answering when generation is needed |
| `nomic-embed-text` | RAG embeddings only |
| Qdrant | Local vector storage |
| Obsidian | Optional human knowledge surface, not runtime dependency |

Before restarting services, state what will be restarted and why.

Useful checks:

```bash
ollama list
ollama ps
curl -fsS http://localhost:11434/api/tags
docker compose -f docker/docker-compose.qdrant.yml ps
curl -fsS http://localhost:6333/healthz
```

---

## 8. Documentation Map

| File | Purpose |
|---|---|
| `docs/04_MEM/AGENT_CONTEXT.md` | Shared agent memory and A2A coordination rules |
| `docs/04_MEM/current_state.md` | Live project state at end of sessions |
| `docs/04_MEM/decisions.md` | Decision log and rationale |
| `docs/04_MEM/next_actions.md` | Immediate next actions |
| `CLAUDE.md` | Claude-specific local instructions |
| `AGENTS.md` | Agent-facing repository instructions when present |
| `.codex/instructions.md` | Codex-specific local instructions when present |

If these files disagree, prefer this order:

1. Human's latest explicit instruction.
2. Security rules.
3. `docs/04_MEM/decisions.md`.
4. `docs/04_MEM/current_state.md`.
5. `docs/04_MEM/AGENT_CONTEXT.md`.
6. Tool-specific files such as `CLAUDE.md`, `AGENTS.md`, `.codex/instructions.md`.

---

## 9. Session Handoff Template

Append or paste this at the end of substantial sessions:

```markdown
## Handoff — YYYY-MM-DD

**Agent:** Codex | Claude | Human | ChatGPT Thinking
**Branch:** `<branch>`
**Issue/PR:** #...
**Task:** one sentence

### Changed
- `path`: what changed

### Validation
- `command`: result

### Not Changed
- Forbidden files untouched.
- No real data used.
- No remote AI used.

### Next Action
- One concrete next step.

### Risks
- Remaining risk or "none known".
```

---

## 10. Update Rules for This File

- Keep this file concise and durable.
- Do not paste transient logs here.
- Do not store secrets or private data here.
- Update only coordination rules, stable project context, and handoff protocol.
- Put volatile sprint status in `current_state.md`.
- Put architectural rationale in `decisions.md`.

---

## Handoff — 2026-04-26

**Agent:** Claude (Cowork)  
**Branch:** `feat/rag-retriever-context`  
**Issue/PR:** #10 / PR #11  
**Task:** Review RAG-04 — Retriever + ContextPacker; approve for merge.

### Changed
- `docs/04_MEM/AGENT_CONTEXT.md`: section 4 table updated — RAG-01–03 marked merged, RAG-04 ready to merge, RAG-05 next.

### Validation
- PR #11 diff reviewed: `context_packer.py`, `retriever.py`, `test_context_packer.py`, `test_retriever.py`, `current_state.md`.
- 31 passed, 3 subtests passed (validated locally by Codex + human).
- mypy strict: 0 issues. pyright: 0 errors. py_compile: passed. git diff --check: passed.
- No forbidden files touched. No LangChain, sentence-transformers, remote AI, or real data.

### Not Changed
- `CLAUDE.md`, `.claude/`, `.env`, dependencies, `uv.lock` untouched.
- No real portfolio data accessed.

### Next Action
- Human merges PR #11 (`gh pr merge 11 --squash --delete-branch` or equivalent).
- Open issue #12 for RAG-05: PromptBuilder + LocalGenerator.

### Risks
- Smoke tests with real Ollama + Docker Qdrant remain for RAG-06.
- None known for this PR.

---

## Handoff — 2026-04-26

**Agent:** Codex
**Branch:** `feat/rag-local-pipeline-smoke`
**Issue/PR:** #12 / PR pending
**Task:** RAG-05 — close local RAG path with prompt, local generator, pipeline, and fake smoke test.

### Changed
- `backend/rag/prompt_builder.py`: builds local RAG chat messages with `/no_think`, context blocks, and citations.
- `backend/rag/generator.py`: adds local Ollama `/api/chat` client with `stream=false`, timeout, temperature, and `<think>` stripping when thinking mode is off.
- `backend/rag/pipeline.py`: orchestrates retriever -> prompt builder -> generator and returns answer, chunks, citations, messages, and latency.
- `tests/unit/test_prompt_builder.py`: prompt formatting tests.
- `tests/unit/test_generator.py`: mocked Ollama chat tests.
- `tests/smoke/test_rag_pipeline_smoke.py`: fake end-to-end smoke test with no Ollama/Qdrant requirement.
- `AGENTS.md`: compact OpenAI/Codex memory entrypoint.

### Validation
- Targeted PR tests passed: 12 passed.
- mypy strict on new files passed.
- pyright on new files passed.

### Not Changed
- `CLAUDE.md`, `.claude/`, `.env`, dependencies, real data, and remote AI untouched.

### Next Action
- Run full validation, commit, push, and open draft PR for Claude independent testing.

### Risks
- Real Ollama + real Qdrant end-to-end remains for a later smoke/CLI PR.

---

## Handoff — 2026-04-26

**Agent:** Codex
**Branch:** `feat/rag-cli-smoke`
**Issue/PR:** #14 / PR pending
**Task:** RAG-06 — executable synthetic ingest/query scripts plus smoke/integration coverage for local RAG proof of life.

### Changed
- `backend/rag/synthetic_documents.py`: five fictional PT-BR finance documents and Qdrant-ready chunk conversion.
- `scripts/rag_ingest_synthetic.py`: async synthetic ingest script for chunk -> embed -> Qdrant upsert, with `--dry-run`.
- `scripts/rag_ask_local.py`: local RAG CLI for question -> retrieval -> prompt -> generation, with `--top-k`, `--thinking`, `--model`, `--verbose`.
- `tests/integration/test_rag_pipeline.py`: complete deterministic pipeline with in-memory Qdrant and fakes.
- `tests/smoke/test_rag_smoke.py`: three-query smoke plus `thinking_mode=True` and empty retrieval paths.
- `docs/04_MEM/current_state.md`: RAG-06 status and RAG-07 validation debt.

### Validation
- Targeted RAG-06 tests passed: 5 passed.
- `rag_ingest_synthetic.py --dry-run` passed.
- `rag_ask_local.py --help` passed.
- mypy strict and pyright on new files passed.

### Not Changed
- `CLAUDE.md`, `.claude/`, `.env`, dependencies, real data, and remote AI untouched.
- No LiteLLM, Redis, FastAPI, LangChain, or sentence-transformers.

### Next Action
- Run full validation, commit, push, and open draft PR for Claude independent testing.

### Risks
- Real Ollama + Docker Qdrant script execution should be checked by Claude/human when local services are running.
- `_validate_question` is intentionally duplicated in RAG-06; extraction to `backend/rag/_validation.py` is registered for RAG-07.

---

## Handoff — 2026-04-26

**Agent:** Codex
**Branch:** `feat/rag-docs-runbook`
**Issue/PR:** #18 / PR pending
**Task:** RAG-07 — runbook, ADR, shared question validation, and health tests.

### Changed
- `backend/rag/_validation.py`: shared `validate_question`.
- `backend/rag/prompt_builder.py`, `backend/rag/pipeline.py`, `backend/rag/retriever.py`: use shared validation.
- `tests/unit/test_validation.py`: shared validation tests.
- `tests/unit/test_health.py`: health preflight tests with mocked httpx.
- `docs/RAG_RUNBOOK.md`: local RAG operation guide.
- `docs/ADR/001-rag-local-only.md`: local-only RAG ADR.

### Validation
- `.venv/bin/python -m unittest tests.unit.test_validation tests.unit.test_health -v` passed.
- `.venv/bin/python -m py_compile backend/rag/*.py scripts/*.py tests/unit/*.py tests/integration/*.py tests/smoke/*.py` passed.
- `git diff --check` passed.

### Not Changed
- `CLAUDE.md`, `.claude/`, `.env`, dependencies, real data, and remote AI untouched.

### Next Action
- Reinstall/sync dev tooling if needed, then run full pytest/mypy/pyright and open PR.

### Risks
- Current `.venv` lacks pytest, mypy, and pyright after manual environment sync, so full validation is pending.

---

## Handoff — 2026-04-26

**Agent:** Claude (Cowork)
**Branch:** `feat/gateway-route-opencraw-litellm` (GW-03) + `feat/gateway-install-health` (GW-02) + `feat/gateway-prep-contracts` (GW-01)
**Issue/PR:** GW-01 / GW-02 / GW-03 — all pending commit via user terminal (git index.lock held by Claude Code process)
**Task:** Gateway-0 — architectural review, risk resolution, and all corrections for GW-01/02/03.

### Changed

**GW-01 — `feat/gateway-prep-contracts`**
- `backend/gateway/config.py`: Pydantic v2 schema for `litellm_config.yaml`; `LiteLLMParams.must_be_local` rejects non-localhost `api_base`; `GatewayConfig.required_aliases_present` enforces all 5 aliases at load time; `load_gateway_config()` wraps failures in `GatewayConfigurationError`; `get_alias()` raises `GatewayModelAliasError`.
- `backend/gateway/health.py`: `check_gateway_services()` fetches Ollama `/api/tags`, verifies `qwen3:14b` and `nomic-embed-text` loaded (base-name matching for quantised variants); exits status 1 with actionable `ollama pull` hint on failure.
- `tests/unit/test_gateway_config.py`: 25 tests — schema validation, alias enforcement, contract tests against real `config/litellm_config.yaml`.
- `tests/unit/test_gateway_health.py`: 10 tests — mocked httpx, quantised variant acceptance, connect error, missing models, 503 response.
- `backend/gateway/errors.py`: stable 8-error taxonomy; all subclass `GatewayError` with `alias`/`provider` kwargs and `to_log_context()`; added `GatewayConnectionError` and `GatewayAuthenticationError`.

**GW-02 — `feat/gateway-install-health`**
- `infra/litellm/litellm_config.yaml`: operational runtime config using `os.environ/OLLAMA_API_BASE` (not hardcoded); 5 aliases; `general_settings.master_key: os.environ/LITELLM_MASTER_KEY`.
- `infra/litellm/start_litellm.sh`: refuses missing `LITELLM_MASTER_KEY`, `LITELLM_HOST != 127.0.0.1`, remote `OLLAMA_API_BASE`, remote model override; `set -euo pipefail`.
- `infra/litellm/requirements.txt`: `litellm[proxy]>=1.83.0,<2.0.0,!=1.82.7,!=1.82.8` (supply-chain exclusions).
- `infra/litellm/README.md`: added "Future Directions" section documenting MCP integration sequence.

**GW-03 — `feat/gateway-route-opencraw-litellm`**
- `backend/gateway/client.py`: `GatewayRuntimeConfig` (frozen dataclass, `.from_env()`, `.validated()` rejects non-localhost and empty api_key); `GatewayChatClient` (async httpx, maps errors to domain exceptions; api_key NOT in exception messages).
- `backend/rag/generator.py`: routes through `GatewayChatClient`; **critical fix applied** — `.validated()` called before `httpx.AsyncClient` creation to prevent resource leaks on bad config.
- `config/rag_config.yaml`: `generation.endpoint` → `http://127.0.0.1:4000/v1`; `generation.model` → `local_rag` (semantic alias); `api_key_env` field converted to comment (key set via shell export only).
- `docs/guides/OPENCLAW_LITELLM_RUNTIME.md`: all 6 env vars, start sequence, troubleshooting guide.
- `tests/unit/test_gateway_client.py`: 4 tests — alias/constant purity, rag_config.yaml contract, auth failure without key leak.
- `backend/gateway/__init__.py`: exports all public symbols (client, config, health, all 8 errors).
- `.gitignore`: added `.claude/worktrees/`.
- `docs/04_MEM/AGENT_CONTEXT.md`: sections 3 and 4 updated (LiteLLM gateway assumptions, env vars table, complete sprint history).

### Validation
- `uv run pytest` — **98/98 passed** (all unit + integration + smoke).
- `uv run mypy backend/ --strict --explicit-package-bases` — **0 errors** (35 files checked).
- `uv run pyright backend/` — **0 errors**.
- `git diff --check` — passed.
- No LangChain, sentence-transformers, remote AI, real data, or forbidden files touched.

### Not Changed
- `CLAUDE.md`, `.claude/`, `.env`, `uv.lock`, real portfolio data untouched.
- Embeddings still use direct Ollama (`http://localhost:11434`) — gateway routing for embeddings is GW-04.
- `_validate_messages` duplication between `generator.py` and `GatewayChatClient` intentionally deferred to GW-04.
- FastAPI, Redis, multi-agent production workflows, brokerage integrations: untouched.

### Next Action
- **User must commit via terminal** (git index.lock prevents sandbox git operations):
  ```bash
  # GW-01
  git checkout feat/gateway-prep-contracts
  git add backend/gateway/config.py backend/gateway/health.py backend/gateway/errors.py \
          tests/unit/test_gateway_config.py tests/unit/test_gateway_health.py \
          backend/gateway/__init__.py .gitignore
  git commit -m "feat(gateway): GW-01 — schema validation, health checks, stable error taxonomy"

  # GW-02
  git checkout feat/gateway-install-health
  git add infra/litellm/litellm_config.yaml infra/litellm/start_litellm.sh \
          infra/litellm/requirements.txt infra/litellm/README.md
  git commit -m "feat(gateway): GW-02 — LiteLLM operational config and startup scripts"

  # GW-03
  git checkout feat/gateway-route-opencraw-litellm
  git add backend/gateway/client.py backend/rag/generator.py config/rag_config.yaml \
          docs/guides/OPENCLAW_LITELLM_RUNTIME.md tests/unit/test_gateway_client.py \
          docs/04_MEM/AGENT_CONTEXT.md
  git commit -m "feat(gateway): GW-03 — route OpenClaw runtime through LiteLLM gateway"
  ```
- Open PRs for GW-01, GW-02, GW-03 via `gh pr create`.
- Plan GW-04: consolidate `_validate_messages`, per-alias timeout config, embed routing via `local_embed`.

### Risks
- All git operations pending user terminal execution (index.lock).
- `local_think` timeout (120s) is in litellm_config.yaml but `GatewayChatClient` uses global timeout — per-alias timeout is GW-04 scope.
- Real Ollama + Docker Qdrant E2E with live LiteLLM not yet smoke-tested in this environment.

---

## Handoff — 2026-05-01

**Agent:** Codex
**Branch:** `feat/gateway-operational-readiness`
**Issue/PR:** #48 / PR #49
**Task:** GW-12 — Gateway-0 operational readiness close.

### Changed
- `docs/GATEWAY_FINAL_RUNBOOK.md`: boot order, start/stop, env vars, readiness/smoke/rollback commands, RagRunTrace + RagObservabilityEvent interpretation, troubleshooting matrix, security checklist.
- `scripts/check_gateway_readiness.sh`: static default mode (7 checks) + `--live` opt-in (Qdrant/Ollama/LiteLLM + 768-dim quimera_embed verification).
- `tests/unit/test_gateway_readiness_script.py`: 9 static readiness tests.
- `tests/unit/test_gateway_final_baseline.py`: 7 baseline tests — alias coherence, no remote models, RAG config baseline, smoke guards, unified `FORBIDDEN_OBSERVABILITY_KEYS` audit across `RagRunTrace` and `RagObservabilityEvent`, supply chain exclusions.
- `docs/ADR/0019-gateway-0-sprint-boundary.md`: delivered components, architectural boundaries, observability rules, future work list.
- `CLAUDE.md`, `docs/04_MEM/AGENT_CONTEXT.md`, `docs/04_MEM/current_state.md`, `docs/04_MEM/decisions.md`, `docs/04_MEM/next_actions.md`, `docs/04_MEM/GATEWAY0_STATUS.md`, `docs/GATEWAY_SETUP.md`, `docs/guides/OPENCLAW_LITELLM_RUNTIME.md`, `docs/sprints/GATEWAY_SPRINT_HANDOFF.md`: sprint table and status updates.
- `tests/unit/test_litellm_infra_scripts.py`: minor addition.

### Validation
- `uv run pytest tests/` — 231 passed (unit + integration + smoke).
- `uv run mypy backend/ --strict` — 0 errors.
- `uv run pyright backend/` — 0 errors.
- `scripts/check_gateway_readiness.sh` static mode — passed.
- No LangChain, sentence-transformers, remote AI, real data, or forbidden files.

### Not Changed
- No `backend/` module changed.
- No remote providers introduced.
- No Qdrant mutation, no reindexing, no `openclaw_knowledge` access.
- Memory/resource baseline not implemented — deferred post-Gateway-0. See ADR-0019 Future Work.

### Next Action
- Gateway-0 sprint complete. Next sprint requires new issue + ADR/sprint plan.

### Risks
- Live readiness (`--live`) not run in this shell — requires `LITELLM_MASTER_KEY` export and local services running.
- None known for static validation.
