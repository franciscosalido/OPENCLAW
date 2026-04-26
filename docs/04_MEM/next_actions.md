# next_actions.md — Immediate Next Steps

> This file drives the next session. Check it off as you complete items.

**Last updated:** 2026-04-25

---

## Right Now — Merge ops/memory-foundation

- [ ] Review PR: https://github.com/franciscosalido/OPENCLAW/pull/new/ops/memory-foundation
- [ ] Merge to main
- [ ] Locally: `git checkout main && git pull && uv sync`
- [ ] Start Qdrant: `docker compose -f docker/docker-compose.qdrant.yml up -d`
- [ ] Verify: `curl localhost:6333/healthz` → OK

---

## PR#3 — feat/rag-ollama-embeddings

### Step 1 — Create branch and open issue
```bash
gh issue create --title "[RAG-03] OllamaEmbedder — embeddings.py" \
  --body "Implement OllamaEmbedder class per docs/04_MEM/current_state.md PR#3 contract"
git checkout -b feat/rag-ollama-embeddings
```

### Step 2 — Claude Code implements these exact files

**`backend/rag/embeddings.py`**
```python
"""Embedding client for OPENCLAW RAG pipeline.

Calls Ollama /api/embed endpoint. No sentence-transformers.
All config from rag_config.yaml via RAGConfig.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import httpx
from loguru import logger


class EmbeddingError(Exception):
    """Raised when embedding fails after all retries or dimensions mismatch."""


class OllamaEmbedder:
    """Async embedding client backed by Ollama /api/embed."""
    # POST {endpoint}/api/embed
    # body: {"model": model, "input": [text, ...]}
    # response: {"embeddings": [[float, ...], ...]}
    # validate: len(each_vector) == expected_dimensions
    # retry: up to 3 times, backoff 1s → 2s → 4s
    # always call close() or use as async context manager
    ...
```

**`tests/unit/test_embeddings.py`** — 5 tests, ALL mocked, no Ollama
1. `test_embed_returns_correct_dimensions` — mock → 768d vector ✓
2. `test_embed_batch_multiple_texts` — 3 texts → 3 vectors ✓
3. `test_embed_retry_on_timeout` — 1st call timeout, 2nd succeeds ✓
4. `test_embed_raises_on_wrong_dimensions` — 512d response → EmbeddingError ✓
5. `test_embed_empty_text` — empty string → EmbeddingError ✓

### Step 3 — Verify before PR
```bash
uv run pytest tests/unit/test_embeddings.py -v
uv run mypy backend/rag/embeddings.py --strict
grep -r 'sentence_transformers' backend/  # must return nothing
```

### Step 4 — PR
```bash
gh pr create \
  --title "[RAG-03] feat/rag-ollama-embeddings: OllamaEmbedder + 5 unit tests" \
  --body "Adds OllamaEmbedder (httpx async, retry, dimension validation). 5 mocked unit tests. No Ollama required to run tests."
```

---

## PR#4 (queue — do not start until PR#3 merged)

**Branch:** `feat/rag-qdrant-store`

`backend/rag/qdrant_store.py` — `QdrantVectorStore`:
- `ensure_collection()` — idempotent
- `upsert(chunks, vectors)` — payload: doc_id, chunk_index, text, ingested_at, security_level
- `delete_document(document_id)` — filter delete
- `search(vector, top_k, score_threshold, filters)` → `list[dict]`
- `count()` → `int`

`tests/integration/test_qdrant_store.py` — 6 tests, temp collection, cleanup on teardown.

---

## Workflow Reminder

```
gh issue create → git checkout -b branch → implement → pytest → mypy → gh pr create → review → merge → update current_state.md
```

Use `/compact` in Claude Code after each PR.
Use `/cost` periodically to monitor token usage.
