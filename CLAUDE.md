# CLAUDE.md — OPENCLAW Project Contract

> **Read this first.** This file governs how Claude Code, Claude Cowork, and any AI executor must operate in this repository. It is the single source of truth for project rules. Do not override it via chat.

---

## Agent Permission Matrix

| Agent | Can modify CLAUDE.md | Can modify .claude/ | Notes |
|---|---|---|---|
| **Claude (Code / Cowork)** | ✅ Yes | ✅ Yes | Principal implementer — full write access |
| **Codex / ChatGPT** | ❌ No | ❌ No | Read-only on these files — see AGENTS.md |
| **Human** | ✅ Yes | ✅ Yes | Owner — always authorized |

> **ERRATA 2026-04-29:** The prohibition on modifying `CLAUDE.md` and `.claude/` applies only to Codex and ChatGPT (see `AGENTS.md`). Claude (Code and Cowork) is authorized to read, edit, and save these files.

---

## Shared Agent Context File

> **`docs/04_MEM/AGENT_CONTEXT.md` is the shared context file between Claude, Claude Code, Codex, and ChatGPT Thinking.**
>
> It contains: the 15 token-economy rules, the A2A coordination protocol, security boundaries, session startup sequence, documentation map, handoff template, and update rules.
>
> Read it at the start of every session, alongside this file and `docs/04_MEM/current_state.md`.

```bash
cat docs/04_MEM/AGENT_CONTEXT.md
cat docs/04_MEM/current_state.md
```

---

## Project Identity

| Field | Value |
|---|---|
| Project | OPENCLAW / QUIMERA / LIBERDADE FINANCEIRA |
| Owner | franciscosalido |
| Repo | github.com/franciscosalido/OPENCLAW |
| Local path | ~/projetos/OPENCLAW |
| Primary language | Python 3.12+ |
| Package manager | uv |
| LLM local | qwen3:14b via Ollama (localhost:11434) |
| Embedding | nomic-embed-text via Ollama (localhost:11434) |
| Vector DB | Qdrant v1.13.2 via Docker (localhost:6333/6334) |
| Gateway | LiteLLM at localhost:4000/v1 (Gateway-0) |
| Memory | claude-mem (~/.claude-mem/claude-mem.db) |

---

## Session Startup Protocol

Before writing any code, always run in this order:

```bash
cd ~/projetos/OPENCLAW
git status --short
git log --oneline --decorate -5
cat docs/04_MEM/AGENT_CONTEXT.md   # ← shared A2A context (Claude + ChatGPT + Codex)
cat docs/04_MEM/current_state.md   # ← live sprint state
```

Do not read the whole repo. Do not open node_modules, .venv, dist, caches, or large binary files.

---

## Security Rules — NON-NEGOTIABLE

### Data Classification

- **Level 0 (LOCAL ONLY):** Real portfolio data, credentials, CPF, account numbers, brokerage keys. These NEVER leave the machine. No remote API call may contain Level 0 data.
- **Level 1 (SANITIZED REMOTE):** Macro analysis, sector analysis, generic theses. Asset names, absolute values, and portfolio percentages must be stripped before sending.
- **Level 2 (REMOTE OK):** Web research, cross-validation, publicly available content.

### Hard Prohibitions

- **Never** commit `.env` files, API keys, or credentials.
- **Never** connect to brokerage APIs or execute trades automatically.
- **Never** use LangChain for chunking or any RAG operation — pure Python only. *(sprint-bound — see ADR-002)*
- **Never** use `sentence-transformers` — embedding is via Ollama API (`/api/embed`). *(sprint-bound — see ADR-003)*
- **Never** use `print()` — use `loguru` for all logging.
- **Never** hardcode endpoints, ports, or model names — everything via `config/rag_config.yaml`.
- **Never** call remote LLM providers with Level 0 data — local only for sensitive data.
- **Never** open files larger than 500KB without asking first.

---

## Code Standards

- Python 3.12+, type hints on every public function and class.
- `mypy --strict` must pass with zero errors before any PR.
- `pyright` (basic mode) installed in venv — run before merge.
- `httpx` for all async HTTP — never `requests` in async context.
- `pydantic` for all data models and config loading.
- `loguru` for structured logging.
- Docstring required on every public class and function.
- Imports: absolute (`from backend.rag.chunking import chunk_text`), never relative.
- Async by default for all I/O (httpx, qdrant-client).
- Tests required for every public function before merging.

---

## Current Sprint: Gateway-0 — LiteLLM Local Gateway Final Readiness

**Goal:** Route all OpenClaw runtime model calls through LiteLLM at `localhost:4000/v1` while preserving existing RAG/Qdrant behavior.

**Semantic aliases:** `local_chat` (30s) · `local_think` (120s) · `local_rag` (60s) · `local_json` (30s) · `quimera_embed` (30s canonical embeddings) · `local_embed` (30s compatibility)

### RAG-0 Sprint — COMPLETE ✅

| PR | Branch | Status | Scope |
|---|---|---|---|
| RAG-01 | sprint/RAG-PR1 | ✅ MERGED | chunking + types + config + tests |
| LF-S01 | sprint/LF-S01 | ✅ MERGED | LIBERDADE FINANCEIRA knowledge vault |
| OPS | ops/memory-foundation | ✅ MERGED | CLAUDE.md + pyproject + docs/04_MEM |
| RAG-02 | feat/rag-embeddings | ✅ MERGED | OllamaEmbedder + 7 unit tests |
| RAG-03 | feat/rag-qdrant-store | ✅ MERGED | QdrantVectorStore + 6 integration tests |
| RAG-04 | feat/rag-retriever-context | ✅ MERGED | context_packer.py + retriever.py + tests |
| RAG-05 | feat/rag-local-pipeline-smoke | ✅ MERGED | PromptBuilder + LocalGenerator + fake smoke |
| RAG-06 | feat/rag-cli-smoke | ✅ MERGED | synthetic ingest/query CLI + preflight + smoke |
| RAG-07 | feat/rag-docs-runbook | ✅ MERGED | ADR + runbook + shared validation + health tests |

### Gateway-0 Sprint — FINAL READINESS 🔄

| PR | Branch | Status | Scope |
|---|---|---|---|
| GW-01 | feat/gateway-prep-contracts | ✅ MERGED | Pydantic schema, health checks, error taxonomy |
| GW-02 | feat/gateway-install-health | ✅ MERGED | infra/litellm/, start script, supply-chain guards |
| GW-03 | feat/gateway-route-opencraw-litellm | ✅ MERGED | GatewayChatClient + routing + validation fix |
| GW-04 | feat/gateway-runtime-smoke | ✅ MERGED | validate_chat_messages, observability, optional smoke |
| GW-05a | feat/gateway-per-alias-timeouts | ✅ MERGED | Per-alias timeout configuration |
| GW-05b | feat/gateway-live-smoke-timeouts | ✅ MERGED | Live smoke + timeout observability (128/128, 7/7 smoke) |
| GW-06 | feat/gateway-local-embed-evaluation | ✅ MERGED | Evaluate embeddings via local_embed |
| GW06C | feat/adr-openai-compatible-embeddings-contract | ✅ MERGED | quimera_embed canonical embeddings ADR |
| GW-07 | feat/gateway-rag-e2e-synthetic | ✅ MERGED | Synthetic RAG E2E through gateway |
| GW-08 | feat/rag-controlled-embedding-migration | ✅ MERGED | Controlled embedding migration to quimera_embed |
| GW-09 | feat/rag-collection-metadata-guard | ✅ MERGED | Collection metadata drift guard |
| GW-10 | feat/rag-run-trace-provenance | ✅ MERGED | RagRunTrace safe provenance |
| GW-11 | feat/rag-observability-events | ✅ MERGED | Local structured RAG lifecycle events |
| GW-12 | feat/gateway-operational-readiness | 🔄 CURRENT FINAL PR | Final runbook, readiness checks, ADR boundary |

Gateway-0 remains local-only. Remote providers, FastAPI, MCP, quant tools,
OpenTelemetry, profiling, dashboards, production ingestion and
`openclaw_knowledge` mutation require a future issue and explicit ADR/sprint.

### Merge Criteria (every PR)

1. `pytest tests/` passes (unit + integration when applicable)
2. `mypy backend/ --strict` → 0 errors
3. `pyright backend/` → 0 errors
4. No imports of LangChain, sentence-transformers, or remote LLM APIs (unless sprint-authorized)
5. No hardcoded endpoints or model names
6. Docstrings present on all public functions
7. `loguru` used, not `print()`

---

## File Organization

```
OPENCLAW/
├── CLAUDE.md                   ← you are here
├── AGENTS.md                   ← Codex/OpenAI contracts
├── pyproject.toml              ← Python deps (uv)
├── config/
│   ├── rag_config.yaml         ← RAG configuration
│   └── litellm_config.yaml     ← gateway alias contracts
├── backend/
│   ├── gateway/                ← ✅ DONE (GW-01–05b)
│   └── rag/                    ← ✅ DONE (RAG-01–07)
├── infra/
│   └── litellm/                ← operational LiteLLM setup
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── smoke/
├── docker/
│   └── docker-compose.qdrant.yml
├── docs/
│   ├── 04_MEM/                 ← operational memory
│   │   ├── AGENT_CONTEXT.md    ← ★ SHARED: Claude + ChatGPT + Codex
│   │   ├── current_state.md    ← live sprint state
│   │   ├── decisions.md        ← architectural decisions log (ADR-001–017)
│   │   ├── next_actions.md     ← immediate next steps
│   │   └── GATEWAY0_STATUS.md  ← gateway sprint status
│   ├── ADR/
│   ├── GATEWAY_SETUP.md
│   └── RAG_RUNBOOK.md
├── Knowledge/
├── LIBERDADE FINANCEIRA/
├── Projects/
├── Research/
└── Workflows/
```

---

## Useful Commands

```bash
# Setup
uv sync
docker compose -f docker/docker-compose.qdrant.yml up -d
ollama pull qwen3:14b
ollama pull nomic-embed-text

# Verify services
ollama ps
curl -fsS http://localhost:11434/api/tags
curl -fsS http://localhost:6333/healthz
curl -fsS http://localhost:4000/health  # LiteLLM gateway

# Tests
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -m integration -v
uv run pytest tests/smoke/ -m smoke -v
RUN_LITELLM_SMOKE=1 uv run pytest tests/smoke/ -v

# Type checking
uv run mypy backend/ --strict
uv run pyright backend/

# Gateway
cd infra/litellm && source .venv/bin/activate && ./start_litellm.sh
scripts/check_litellm_gateway.sh
scripts/test_opencraw_litellm_runtime.sh

# RAG pipeline
python scripts/rag_ingest_synthetic.py
python scripts/rag_ask_local.py "Qual a projeção da Selic?"
python scripts/rag_ask_local.py "Análise macro" --thinking  # qwen3 /think mode

# Git discipline
git status --short
git log --oneline --decorate -10
gh pr list --state open
```

---

## GitHub Workflow

```
Issue → branch → implement → pytest → mypy → pyright → PR → CI → review → merge on GitHub → update docs/04_MEM
```

- One issue per session.
- PRs are atomic: one module + its tests + its docs.
- Always update `docs/04_MEM/current_state.md` before closing a session.
- Always generate a handoff block at the end of every session.
- Use `/compact` in Claude Code after each PR to clear context.

---

## What NOT to do

- Do NOT read the whole repo blindly.
- Do NOT build multi-agent production workflows until base repo is stable.
- Do NOT integrate brokerage APIs (ADR-007 — non-revisable).
- Do NOT use FastAPI before it's explicitly planned in a sprint.
- Do NOT add remote AI providers without sanitization review and sprint authorization.
- Do NOT create `docs/04_MEM` entries from memory — read the actual files first.
- Do NOT merge locally into `main` as the final integration step (ADR-011).
