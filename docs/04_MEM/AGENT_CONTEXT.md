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
- Local LLM runtime: Ollama.
- Primary local generation model: `qwen3:14b`.
- Embedding model: `nomic-embed-text`.
- Vector database: Qdrant.
- Mathematical co-processor: deterministic Python modules.
- Remote AI: sanitized fallback only in a future Gateway sprint.
- GitHub is the source of truth for issues, branches, PRs, and merge state.

---

## 4. Sprint RAG-0 Direction

Canonical pipeline:

```text
SyntheticDocument
  -> Chunker
  -> Ollama Embeddings
  -> Qdrant VectorStore
  -> Retriever
  -> ContextPacker
  -> PromptBuilder
  -> LocalGenerator
  -> AnswerWithCitations
```

Near-term PR sequence:

| PR | Branch | Scope | Status |
|---|---|---|---|
| RAG-01 | `feat/rag-chunking-*` | Chunking + tests | Merged ✅ |
| RAG-02 | `feat/rag-embeddings` | Ollama embeddings + tests | Merged ✅ |
| RAG-03 | `feat/rag-qdrant-store` | Qdrant store + integration tests | Merged ✅ |
| RAG-04 | `feat/rag-retriever-context` | Retriever + ContextPacker | Merged ✅ |
| RAG-05 | `feat/rag-local-pipeline-smoke` | PromptBuilder + LocalGenerator + fake smoke | Merged ✅ |
| RAG-06 | `feat/rag-cli-smoke` | Synthetic ingest/query CLI + smoke | Merged ✅ |
| RAG-07 | `feat/rag-docs-runbook` | Runbook + ADR + validation cleanup | Active PR prep |

Before starting a PR, confirm actual state with:

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
- Prefer clean worktrees based on `origin/main`.
- Keep diffs small enough to review in one pass.
- Do not commit or push unless explicitly instructed.
- Do not merge unless explicitly instructed.
- If a branch depends on an open PR, say so before implementing.

Recommended branch shape:

```text
feat/rag-<small-scope>
docs/<small-scope>
fix/<small-scope>
```

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
