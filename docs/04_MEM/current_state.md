# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human review.
> Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of meaningful sessions.

**Last updated:** 2026-04-26
**Updated by:** Codex — RAG-05 local pipeline smoke prep

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
| RAG-01 | `feat/rag-chunking-*` | Merged | Chunking + unit tests |
| RAG-02 | `feat/rag-embeddings` | Merged | Ollama embeddings + mocked unit tests |
| RAG-03 | `feat/rag-qdrant-store` | Merged | Qdrant store + integration tests |
| RAG-04 | `feat/rag-retriever-context` | Merged | Retriever + ContextPacker |
| RAG-05 | `feat/rag-local-pipeline-smoke` | Active PR prep | PromptBuilder + LocalGenerator + LocalRagPipeline + fake smoke |
| RAG-06 | `feat/rag-cli-smoke` | Planned | Synthetic ingest/query CLI + real local smoke |
| RAG-07 | `feat/rag-docs-runbook` | Planned | Runbook + ADR + final checklist |

Current issue for active work: <https://github.com/franciscosalido/OPENCLAW/issues/12>

---

## What Exists in `main` Now

```text
backend/rag/
  __init__.py
  chunking.py
  context_packer.py
  embeddings.py
  qdrant_store.py
  retriever.py

tests/
  unit/test_chunking.py
  unit/test_context_packer.py
  unit/test_embeddings.py
  unit/test_retriever.py
  integration/test_qdrant_store.py

config/rag_config.yaml
docker/docker-compose.qdrant.yml
docs/04_MEM/AGENT_CONTEXT.md
docs/04_MEM/current_state.md
docs/04_MEM/decisions.md
docs/04_MEM/next_actions.md
```

---

## Active Branch: `feat/rag-local-pipeline-smoke`

Planned files for PR #12:

```text
backend/rag/prompt_builder.py
backend/rag/generator.py
backend/rag/pipeline.py
tests/unit/test_prompt_builder.py
tests/unit/test_generator.py
tests/smoke/test_rag_pipeline_smoke.py
AGENTS.md
docs/04_MEM/AGENT_CONTEXT.md
docs/04_MEM/current_state.md
```

Current implementation summary:

- `PromptBuilder` formats context blocks with citations and uses `/no_think` by default.
- `LocalGenerator` calls Ollama `/api/chat` with `stream=false` and can be fully mocked.
- `LocalRagPipeline` orchestrates retrieval, prompt building, local generation, chunks used, citations, and latency.
- Fake smoke test validates the complete flow without real Ollama or Qdrant.
- Real local service smoke remains for a later CLI/smoke PR.

---

## Latest Local Validation

Targeted RAG-05 checks already passed:

```bash
uv run pytest tests/unit/test_prompt_builder.py tests/unit/test_generator.py tests/smoke/test_rag_pipeline_smoke.py -v
```

Result:

```text
12 passed
```

```bash
uv run mypy --explicit-package-bases --strict backend/rag/prompt_builder.py backend/rag/generator.py backend/rag/pipeline.py tests/unit/test_prompt_builder.py tests/unit/test_generator.py tests/smoke/test_rag_pipeline_smoke.py
```

Result:

```text
Success: no issues found in 6 source files
```

```bash
uv run pyright backend/rag/prompt_builder.py backend/rag/generator.py backend/rag/pipeline.py tests/unit/test_prompt_builder.py tests/unit/test_generator.py tests/smoke/test_rag_pipeline_smoke.py
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

---

## Next Action

Codex should run full validation, open a draft PR, and hand it to Claude for independent testing.

Suggested Claude commands after PR opens:

```bash
git fetch --prune
git checkout feat/rag-local-pipeline-smoke
git pull --ff-only
uv run pytest -v
uv run mypy --explicit-package-bases --strict backend/rag tests/unit tests/integration tests/smoke
uv run pyright backend/rag tests/unit tests/integration tests/smoke
uv run python -m py_compile backend/rag/*.py tests/unit/*.py tests/integration/*.py tests/smoke/*.py
rg -n "LangChain|sentence_transformers|openai|anthropic|remote" backend tests || true
```

---

## Remaining Risks

- PR has not yet been reviewed by Claude.
- Real Ollama + Docker Qdrant end-to-end remains for RAG-06.
- No real data has been used or accessed.
