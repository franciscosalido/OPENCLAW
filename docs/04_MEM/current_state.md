# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human review.
> Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of meaningful sessions.

**Last updated:** 2026-04-26
**Updated by:** Codex — PR #10 preparation

---

## Active Sprint: RAG-0

**Goal:** Full local pipeline: chunk -> embed -> Qdrant -> retrieve -> pack context -> prompt -> Qwen3 answer with citations.

**Hard constraints:**
- Local only for RAG-0.
- Ollama only for embeddings/generation.
- Qdrant local for vector storage.
- No LiteLLM, remote providers, FastAPI, LangChain, sentence-transformers, real portfolio data, or private documents.

---

## GitHub State

| RAG step | Branch | State | Scope |
|---|---|---|---|
| RAG-01 | `feat/rag-chunking-*` | Merged | `chunking.py` + unit tests |
| RAG-02 | `feat/rag-embeddings` | Merged | `OllamaEmbedder` + mocked unit tests |
| RAG-03 | `feat/rag-qdrant-store` | Merged | `QdrantVectorStore` + integration tests |
| RAG-04 | `feat/rag-retriever-context` | In review prep | `ContextPacker` + `Retriever` + unit tests |
| RAG-05 | `feat/rag-prompt-generator` | Next | Prompt builder + local generator |
| RAG-06 | `feat/rag-cli-smoke` | Planned | Synthetic ingest/query CLI + smoke tests |
| RAG-07 | `feat/rag-docs-runbook` | Planned | Runbook + ADR + final checklist |

Current issue for active work: <https://github.com/franciscosalido/OPENCLAW/issues/10>

---

## What Exists in `main` Now

```text
backend/rag/
  __init__.py
  chunking.py
  embeddings.py
  qdrant_store.py

tests/
  unit/test_chunking.py
  unit/test_embeddings.py
  integration/test_qdrant_store.py

config/rag_config.yaml
docker/docker-compose.qdrant.yml
docs/04_MEM/AGENT_CONTEXT.md
docs/04_MEM/current_state.md
docs/04_MEM/decisions.md
docs/04_MEM/next_actions.md
```

---

## Active Branch: `feat/rag-retriever-context`

Planned files for PR #10:

```text
backend/rag/context_packer.py
backend/rag/retriever.py
tests/unit/test_context_packer.py
tests/unit/test_retriever.py
docs/04_MEM/current_state.md
```

Current implementation summary:

- `ContextPacker` is pure Python and deterministic.
- It deduplicates retrieved chunks with Jaccard similarity over tokens.
- It keeps the higher-scoring chunk when two chunks are near-duplicates.
- It truncates context by token budget.
- It reorders final chunks by document id and chunk index for prompt readability.
- `Retriever` orchestrates query embedding, vector search, result conversion, packing, and latency logging.
- Retriever dependencies are injected and testable with fakes.
- No Ollama or Qdrant real service is required for unit tests.

---

## Latest Local Validation

Run on 2026-04-26 from `/Users/fas/projetos/OPENCLAW`:

```bash
uv run pytest -v
```

Result:

```text
31 passed, 3 subtests passed
```

```bash
uv run mypy --explicit-package-bases --strict backend/rag tests/unit tests/integration
```

Result:

```text
Success: no issues found in 11 source files
```

```bash
uv run pyright backend/rag tests/unit tests/integration
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

---

## Next Action

Claude should review and independently test PR #10 after Codex opens it.

Suggested Claude commands:

```bash
git fetch --prune
git checkout feat/rag-retriever-context
git pull --ff-only
uv run pytest -v
uv run mypy --explicit-package-bases --strict backend/rag tests/unit tests/integration
uv run pyright backend/rag tests/unit tests/integration
uv run python -m py_compile backend/rag/*.py tests/unit/*.py tests/integration/*.py
rg -n "LangChain|sentence_transformers|openai|anthropic|remote" backend tests || true
```

---

## Remaining Risks

- PR #10 has not yet been reviewed by Claude.
- Smoke tests with real Ollama + Docker Qdrant remain for later RAG-0 PRs.
- No real data has been used or accessed.
