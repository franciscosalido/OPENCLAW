# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human review.
> Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of meaningful sessions.

**Last updated:** 2026-04-26
**Updated by:** Codex — RAG-07 runbook/validation prep

---

## Active Sprint: RAG-0

**Goal:** Full local pipeline: chunk -> embed -> Qdrant -> retrieve -> pack context -> prompt -> Qwen3 answer with citations.

**Hard constraints:**
- Local only for RAG-0.
- Ollama only for embeddings/generation.
- Qdrant local for vector storage.
- No LiteLLM, remote providers, FastAPI, LangChain, sentence-transformers, Redis, real portfolio data, or private documents.

---

## GitHub State

| RAG step | Branch | State | Scope |
|---|---|---|---|
| RAG-01 | `feat/rag-chunking-*` | Merged | Chunking + unit tests |
| RAG-02 | `feat/rag-embeddings` | Merged | Ollama embeddings + mocked unit tests |
| RAG-03 | `feat/rag-qdrant-store` | Merged | Qdrant store + integration tests |
| RAG-04 | `feat/rag-retriever-context` | Merged | Retriever + ContextPacker |
| RAG-05 | `feat/rag-local-pipeline-smoke` | Merged | PromptBuilder + LocalGenerator + LocalRagPipeline |
| RAG-06 | `feat/rag-cli-smoke` | Merged | Synthetic ingest/query scripts + smoke |
| RAG-07 | `feat/rag-docs-runbook` | Active PR prep | Runbook + ADR + validation cleanup |

Current issue for active work: <https://github.com/franciscosalido/OPENCLAW/issues/18>

---

## Active Branch: `feat/rag-docs-runbook`

Planned files:

```text
backend/rag/_validation.py
backend/rag/prompt_builder.py
backend/rag/pipeline.py
backend/rag/retriever.py
tests/unit/test_validation.py
tests/unit/test_health.py
docs/RAG_RUNBOOK.md
docs/ADR/001-rag-local-only.md
docs/04_MEM/AGENT_CONTEXT.md
docs/04_MEM/current_state.md
```

Current implementation summary:

- `_validate_question` duplication was removed.
- `validate_question` now lives in `backend/rag/_validation.py`.
- PromptBuilder, LocalRagPipeline, and Retriever use the shared helper.
- `health.py` has mocked unit coverage for healthy services, missing Qdrant, missing embedding model, and skipped checks.
- `docs/RAG_RUNBOOK.md` documents local setup, ingest, query, validation, troubleshooting, and thinking-mode policy.
- `docs/ADR/001-rag-local-only.md` records the local-only RAG decision.

---

## Validation Status

Passed in current environment:

```bash
.venv/bin/python -m unittest tests.unit.test_validation tests.unit.test_health -v
.venv/bin/python -m py_compile backend/rag/*.py scripts/*.py tests/unit/*.py tests/integration/*.py tests/smoke/*.py
git diff --check
```

Pending because current `.venv` lacks dev tools after manual sync:

```bash
uv run pytest -v
uv run mypy --explicit-package-bases --strict backend/rag scripts tests/unit tests/integration tests/smoke
uv run pyright backend/rag scripts tests/unit tests/integration tests/smoke
```

Do not install dependencies without explicit human approval.

---

## Remaining Risks

- Full pytest/mypy/pyright validation is pending until dev tools are restored.
- No real data has been used or accessed.
