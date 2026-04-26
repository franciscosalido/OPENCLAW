# CLAUDE.md — OPENCLAW Project Contract

> **Read this first.** This file governs how Claude Code, Claude Cowork, and any AI executor must operate in this repository. It is the single source of truth for project rules. Do not override it via chat.

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
- **Never** use LangChain for chunking or any RAG operation — pure Python only.
- **Never** use `sentence-transformers` — embedding is via Ollama API (`/api/embed`).
- **Never** use `print()` — use `loguru` for all logging.
- **Never** hardcode endpoints, ports, or model names — everything via `config/rag_config.yaml`.
- **Never** call remote LLM providers (Claude API, OpenAI) in RAG-0 — local only.
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

## Current Sprint: RAG-0 — Local Synthetic RAG

**Goal:** Prove the full pipeline: chunk → embed → Qdrant → retrieve → prompt → Qwen3 response with citations.

**Stack for this sprint:**
- Ollama direct (no LiteLLM yet)
- Qdrant v1.13.2 Docker
- nomic-embed-text (768d)
- qwen3:14b — `/no_think` by default for RAG, `/think` only for analytical mode
- Python + httpx + qdrant-client

**LiteLLM enters in Gateway-0 (next sprint).**

### PR Sequence

| PR | Branch | Status | Scope |
|---|---|---|---|
| RAG-01 | sprint/RAG-PR1 | ✅ MERGED | chunking + types + config + tests |
| LF-S01 | sprint/LF-S01 | ✅ MERGED | LIBERDADE FINANCEIRA knowledge vault |
| OPS | ops/memory-foundation | ✅ MERGED | CLAUDE.md + pyproject + docs/04_MEM |
| RAG-02 | feat/rag-embeddings | ✅ MERGED | OllamaEmbedder + 7 unit tests |
| RAG-03 | feat/rag-qdrant-store | ✅ MERGED | QdrantVectorStore + 6 integration tests |
| RAG-04 | feat/rag-retriever-context | ⏳ NEXT | context_packer.py + retriever.py + tests |
| RAG-05 | feat/rag-prompt-generator | ⏳ TODO | prompt_builder.py + generator.py |
| RAG-06 | feat/rag-cli-smoke | ⏳ TODO | scripts + smoke test E2E |
| RAG-07 | feat/rag-docs-runbook | ⏳ TODO | ADR + runbook + acceptance checklist |

### Merge Criteria (every PR)

1. `pytest tests/` passes (unit + integration when applicable)
2. `mypy backend/ --strict` → 0 errors
3. `pyright backend/` → 0 errors
4. No imports of LangChain, sentence-transformers, or remote LLM APIs
5. No hardcoded endpoints or model names
6. Docstrings present on all public functions
7. `loguru` used, not `print()`

---

## File Organization

```
OPENCLAW/
├── CLAUDE.md                   ← you are here
├── AGENTS.md                   ← multi-agent contracts (future)
├── pyproject.toml              ← Python deps (uv)
├── config/
│   └── rag_config.yaml         ← all RAG configuration
├── backend/
│   └── rag/
│       ├── __init__.py
│       ├── chunking.py         ← ✅ DONE
│       ├── embeddings.py       ← ✅ DONE
│       ├── qdrant_store.py     ← ✅ DONE
│       ├── context_packer.py   ← ⏳ RAG-04
│       ├── retriever.py        ← ⏳ RAG-04
│       ├── prompt_builder.py   ← ⏳ RAG-05
│       └── generator.py        ← ⏳ RAG-05
├── scripts/
│   ├── rag_ingest_synthetic.py ← ⏳ RAG-06
│   └── rag_ask_local.py        ← ⏳ RAG-06
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
│   │   ├── decisions.md        ← architectural decisions log
│   │   └── next_actions.md     ← immediate next steps
│   └── ADR/
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

# Tests
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -m integration -v
uv run pytest tests/smoke/ -m smoke -v

# Type checking
uv run mypy backend/ --strict
uv run pyright backend/

# RAG pipeline (after RAG-06)
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
Issue → branch → implement → pytest → mypy → pyright → PR → review → merge → update docs/04_MEM
```

- One issue per session.
- PRs are atomic: one module + its tests + its docs.
- Always update `docs/04_MEM/current_state.md` before closing a session.
- Always generate a handoff block at the end of every session.
- Use `/compact` in Claude Code after each PR to clear context.

---

## What NOT to do

- Do NOT read the whole repo blindly.
- Do NOT install Redis in V1.
- Do NOT build multi-agent production workflows until base repo is stable.
- Do NOT integrate brokerage APIs.
- Do NOT add LiteLLM before Gateway-0.
- Do NOT use FastAPI before it's explicitly planned in a sprint.
- Do NOT create `docs/04_MEM` entries from memory — read the actual files first.
