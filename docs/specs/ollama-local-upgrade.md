# Ollama Local Upgrade and Qwen3-Embedding-4B Bakeoff

Status: draft  
Scope: local Ollama readiness, upgrade policy and embedding bakeoff contracts.

## Scope

Ollama runs locally and outside Docker. Qdrant runs in Docker. This spec prepares
Qwen3-Embedding-4B as a candidate embedding model while keeping
`nomic-embed-text` as baseline/fallback.

## Latest Stable Policy

- Latest stable is tracked as a curated contract in code.
- Contract last verified: 2026-05-28.
- Current curated stable target: `0.24.0`.
- Known prerelease without conventional suffix: `0.30.0`.
- Version contract file: `infra/ollama/version_contract.yaml`.
- Pre-release versions are ignored by default.
- A pre-release requires `--allow-prerelease` and a PKD/ADR note.
- Upgrade is D2P/reversible and never automatic on import.
- macOS installations may be managed by the Ollama app, Homebrew or standalone
  CLI; the local script reports a plan instead of mutating the installation.

## Readiness

`scripts/check_ollama_readiness.py` checks:

- `ollama --version`, if the CLI exists.
- `GET /api/version`.
- `GET /api/tags`.
- `POST /api/show` for `nomic-embed-text` and `Qwen/Qwen3-Embedding-4B`.
- `POST /api/embed` only when `--allow-embed-probe` is passed.

The readiness output is JSON and excludes query text, document text, payloads,
vectors, embeddings, prompts and answers.

Manual model prerequisite for the 4B bakeoff:

```bash
ollama pull qwen3-embedding:4b
```

Do not auto-pull this model from scripts. The local operator must approve the
download explicitly before live benchmark execution.

The architecture-level model ID remains `Qwen/Qwen3-Embedding-4B`. The Ollama
runtime tag accepted by readiness is `qwen3-embedding:4b`.

## Embedding API Policy

- Use `POST /api/embed`.
- Do not use legacy `/api/embeddings` by default.
- Send `input` as a list for batching.
- Use `keep_alive: "30m"` for benchmark runs.
- Use `truncate: true` unless a truncation-specific benchmark says otherwise.
- Record `load_duration`, `total_duration`, `prompt_eval_count`, dimensions,
  batch size and keep_alive when available.

## Qwen3 Query Instruction

Qwen3 query embeddings may use:

```text
Instruct: Given a Portuguese financial advisory retrieval query, retrieve relevant passages from the Quimera financial knowledge base.
Query: <query>
```

Documents do not receive the query instruction.

## Bakeoff Collection

Preferred single collection:

`quimera_benchmark_embedding_bakeoff_118`

Named vectors:

- `dense_nomic`: 768
- `dense_qwen3_4b`: 2560
- `sparse`: sparse vector

Fallback temporary collections, if mixed dimensions cannot be supported by the
current runner:

- `quimera_benchmark_hybrid_118_nomic`
- `quimera_benchmark_hybrid_118_qwen3_4b`

Forbidden:

- `quimera_knowledge`
- `quimera_knowledge_v2`
- `openclaw_knowledge`

## Benchmark Outputs

Artifact paths:

- `evaluation/results/embedding_bakeoff_qwen3_4b_summary.json`
- `evaluation/results/embedding_bakeoff_qwen3_4b_rows.csv`
- `evaluation/results/embedding_bakeoff_qwen3_4b_report.md`
- `evaluation/results/embedding_bakeoff_qwen3_4b_charts.svg`

Live execution requires:

```bash
RUN_OLLAMA_QWEN3_4B_BAKEOFF=1 uv run python evaluation/compare_embedding_models.py --execute
```

`evaluation/compare_embedding_models.py` implements two modes:

- artifact-only mode by default, which writes TBD-safe artifacts without calling
  Ollama or Qdrant;
- live bakeoff mode with the env/flag above, which calls the Q18 profile runner
  for retrieval scenarios and Ollama `/api/embed` probes for dimension,
  instruction, cold/warm and batching scenarios.

The bakeoff should not be used for a final default decision until the query set
is expanded beyond the small Q18 synthetic corpus. Target at least 150 documents
and 50 queries before treating +/-0.01 NDCG deltas as meaningful.

The current Q18 corpus produced equal dense and hybrid NDCG for both Nomic and
Qwen3-Embedding-4B. That is not a retrieval bug; it means the sparse/BM25 leg
does not yet separate the scenarios on this 56-document corpus. Promotion needs
the expanded corpus above before the hybrid-vs-dense signal can be trusted.

## Non-goals

- No MCP live.
- No PostgreSQL.
- No GraphRAG.
- No reranker.
- No DBSF.
- No Qdrant native RRF default.
- No TurboQuant default.
- No public Ollama exposure.
- No Python Weighted RRF change.
- No protected collection mutation.
