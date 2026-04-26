# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human review.
> Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of meaningful sessions.

**Last updated:** 2026-04-26
**Updated by:** Codex — RAG-06 CLI/smoke prep

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
| RAG-05 | `feat/rag-local-pipeline-smoke` | Merged | PromptBuilder + LocalGenerator + LocalRagPipeline + fake smoke |
| RAG-06 | `feat/rag-cli-smoke` | Active PR prep | Synthetic ingest/query scripts + integration/smoke |
| RAG-07 | `feat/rag-docs-runbook` | Planned | Runbook + ADR + validation debt cleanup |

Current issue for active work: <https://github.com/franciscosalido/OPENCLAW/issues/14>

---

## Active Branch: `feat/rag-cli-smoke`

Planned files for PR #14:

```text
backend/rag/synthetic_documents.py
scripts/rag_ingest_synthetic.py
scripts/rag_ask_local.py
tests/integration/test_rag_pipeline.py
tests/smoke/test_rag_smoke.py
docs/04_MEM/AGENT_CONTEXT.md
docs/04_MEM/current_state.md
```

Current implementation summary:

- `synthetic_documents.py` provides five fictional PT-BR finance documents:
  `selic_projecao`, `fiis_analise`, `rebalanceamento`, `regime_macro`, `risco_concentracao`.
- `rag_ingest_synthetic.py` performs chunk -> embed -> Qdrant upsert with per-document metrics and `--dry-run`.
- `rag_ask_local.py` performs question -> retrieval -> prompt -> local generation and prints chunks, answer, and latency.
- `tests/integration/test_rag_pipeline.py` exercises chunk, embed, upsert, retrieve, prompt, generate, and delete with in-memory Qdrant and fakes.
- `tests/smoke/test_rag_smoke.py` exercises three queries, `thinking_mode=True`, and empty retrieval path.

---

## Thinking Mode Policy

MVP policy:

- Default all RAG factual calls to `/no_think`.
- Use `thinking_mode=True` only when explicitly requested, tested, or later routed by Gateway-0/LiteLLM.
- Future Gateway-0 policy: calls originating from OpenCraw or selected agents may set `thinking_mode=True`; calls that only access RAG/Qdrant should prefer `/no_think`.

RAG-06 covers the `thinking_mode=True` wiring with a smoke test but does not introduce LiteLLM or remote routing.

---

## Latest Local Validation

Targeted RAG-06 checks already passed:

```bash
uv run pytest tests/integration/test_rag_pipeline.py tests/smoke/test_rag_smoke.py -v
```

Result:

```text
5 passed
```

```bash
uv run mypy --explicit-package-bases --strict backend/rag/synthetic_documents.py scripts/rag_ingest_synthetic.py scripts/rag_ask_local.py tests/integration/test_rag_pipeline.py tests/smoke/test_rag_smoke.py
```

Result:

```text
Success: no issues found in 5 source files
```

```bash
uv run pyright backend/rag/synthetic_documents.py scripts/rag_ingest_synthetic.py scripts/rag_ask_local.py tests/integration/test_rag_pipeline.py tests/smoke/test_rag_smoke.py
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

```bash
uv run python scripts/rag_ingest_synthetic.py --dry-run
uv run python scripts/rag_ask_local.py --help
```

Result:

```text
Both commands passed.
```

---

## RAG-07 Tech Debt

- `_validate_question` remains duplicated in `prompt_builder.py`, `pipeline.py`, and `retriever.py`.
- Do not refactor it inside RAG-06.
- Candidate RAG-07 cleanup: extract to `backend/rag/_validation.py` and update tests.

---

## Next Action

Codex should run full validation, open a draft PR, and hand it to Claude for independent testing.

Suggested Claude commands after PR opens:

```bash
git fetch --prune
git checkout feat/rag-cli-smoke
git pull --ff-only
uv run pytest -v
uv run mypy --explicit-package-bases --strict backend/rag scripts tests/unit tests/integration tests/smoke
uv run pyright backend/rag scripts tests/unit tests/integration tests/smoke
uv run python -m py_compile backend/rag/*.py scripts/*.py tests/unit/*.py tests/integration/*.py tests/smoke/*.py
uv run python scripts/rag_ingest_synthetic.py --dry-run
uv run python scripts/rag_ask_local.py --help
rg -n "LangChain|sentence_transformers|from openai|import openai|anthropic|LiteLLM|Redis|FastAPI|remote" backend scripts tests || true
```

Real local service checks when Ollama + Qdrant are running:

```bash
docker compose -f docker/docker-compose.qdrant.yml up -d
uv run python scripts/rag_ingest_synthetic.py
uv run python scripts/rag_ask_local.py "Qual o impacto sintetico da Selic?" --verbose
uv run python scripts/rag_ask_local.py "Riscos de concentracao" --thinking --top-k 3
```

---

## Remaining Risks

- Real Ollama + Docker Qdrant script execution has not yet been run in this session.
- No real data has been used or accessed.
