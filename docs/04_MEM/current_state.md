# current_state.md — OPENCLAW Operational Memory

> Update this file at the end of every session. Claude Code reads this before starting work.

**Last updated:** 2026-04-25
**Updated by:** Claude (Cowork) — ops/memory-foundation branch

---

## Active Sprint: RAG-0

**Goal:** Full pipeline local: chunk → embed → Qdrant → retrieve → prompt → Qwen3 answer with citations.
**Constraint:** Ollama only. No LiteLLM, no remote APIs, no FastAPI, no LangChain.

---

## PR Status

| # | Branch | State | What |
|---|---|---|---|
| 1 | sprint/RAG-PR1 | ✅ MERGED | `chunking.py` + `test_chunking.py` (types, config, overlap) |
| 2 | sprint/LF-S01 | ✅ MERGED | 30 knowledge files `LIBERDADE FINANCEIRA/` |
| ops | ops/memory-foundation | 🔄 OPEN | CLAUDE.md, pyproject.toml, config/, docs/04_MEM/ |
| 3 | feat/rag-ollama-embeddings | ⏳ NEXT | `embeddings.py` + 5 unit tests (mocked) |

---

## What Exists in `main` Right Now

```
backend/rag/
  __init__.py       ✅
  chunking.py       ✅  pure Python, paragraph→sentence, overlap
tests/unit/
  test_chunking.py  ✅
scripts/
  setup-claude-mem.sh
.claude/
  settings.json
  hooks.json
Knowledge/
LIBERDADE FINANCEIRA/   ← 30 files added in PR#2
Projects/ Research/ Workflows/
```

**Not yet in main:**
`embeddings.py`, `qdrant_store.py`, `retriever.py`, `context_packer.py`,
`prompt_builder.py`, `generator.py`, `pyproject.toml`, `config/`, `docker/`

---

## Local Worktree Warning

During branch creation, git reported untracked files:
```
backend/rag/__init__.py
backend/rag/chunking.py
tests/unit/test_chunking.py
```
These exist locally but git treats them as untracked on the `ops/memory-foundation` branch.
After merging this PR, run:
```bash
git checkout main && git pull
```
to realign local and remote.

---

## PR#3 Contract (Ready to Execute)

**Branch:** `feat/rag-ollama-embeddings`

**File 1 — `backend/rag/embeddings.py`**
```
class OllamaEmbedder:
  endpoint: POST http://localhost:11434/api/embed
  body:     {"model": "nomic-embed-text", "input": [texts]}
  response: {"embeddings": [[float, ...], ...]}
  validate: len(embedding) == 768  (config.embedding.expected_dimensions)
  retry:    3x backoff 1s → 2s → 4s
  client:   httpx.AsyncClient, async, close() in destructor
  raises:   EmbeddingError on wrong dimensions or persistent failure
```

**File 2 — `tests/unit/test_embeddings.py`** (5 tests, ALL mocked)
1. `test_embed_returns_correct_dimensions`
2. `test_embed_batch_multiple_texts`
3. `test_embed_retry_on_timeout`
4. `test_embed_raises_on_wrong_dimensions`
5. `test_embed_empty_text`

**Merge criteria:**
- `pytest tests/unit/test_embeddings.py` → 5/5 (no Ollama needed)
- `mypy backend/rag/embeddings.py --strict` → 0 errors
- No `sentence_transformers` import
- `httpx.AsyncClient` with proper `close()`

---

## Environment

| Service | Status |
|---|---|
| Ollama | ✅ installed — qwen3:14b + nomic-embed-text pulled |
| Qdrant | ⚠️ needs `docker compose up` (docker-compose.qdrant.yml added in this PR) |
| Python | 3.12 via uv |
| mypy + pyright | ✅ installed in .venv |
| httpx | ⚠️ will be available after `uv sync` (pyproject.toml added in this PR) |
