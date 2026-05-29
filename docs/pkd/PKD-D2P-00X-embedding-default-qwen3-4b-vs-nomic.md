# PKD-D2P-00X: Embedding Default — Qwen3-Embedding-4B vs Nomic

Status: Proposed  
Decision type: D2P / Two-Way Door / Reversible  
Scope: local-first embedding bakeoff for Quimera / OpenClaw

## Context

Quimera currently keeps `nomic-embed-text` as the baseline embedding model and
Python Weighted RRF as the retrieval ground truth. Qwen3-Embedding-4B is the new
candidate for higher-quality dense retrieval, but it must be benchmarked before
becoming default.

Ollama remains local and outside Docker. Qdrant remains local in Docker. No MCP,
PostgreSQL, GraphRAG, reranker, DBSF, TurboQuant default or Qdrant native RRF
default is introduced by this decision.

## Decision

Prepare Qwen3-Embedding-4B as the primary candidate and keep
`nomic-embed-text` as baseline/fallback until benchmark evidence is complete.

Possible outcomes:

- `promote_qwen3_4b_default`
- `keep_nomic_default`
- `qwen3_4b_experimental_only`
- `inconclusive_qwen3_4b_unavailable`
- `defer_due_to_latency_or_memory`

## Promotion Criteria

Qwen3-Embedding-4B may become default only if:

- Qwen3-Embedding-4B is available locally.
- Output dimension is measured and matches the selected dimension.
- NDCG@5 is at least Nomic + 0.01, or ties within +/-0.005 with stronger
  semantic/human-language query performance.
- The implementation applies a `1e-9` floating-point tolerance around the
  `+0.01` NDCG promotion boundary to avoid IEEE 754 false negatives.
- Recall@10 does not regress against Nomic.
- p95 total latency is at most 2.0x Nomic.
- Cold-start cost is mitigable with `keep_alive`.
- Artifacts do not leak query text, document text, payloads, vectors,
  embeddings, prompts or answers.
- Python Weighted RRF remains ground truth.

Current Q18 evidence is intentionally insufficient for promotion because dense
and hybrid NDCG are equal for both models on the small synthetic corpus. This
suggests the sparse leg is not adding measurable quality yet; the next decision
requires the larger corpus target documented in the Ollama local upgrade spec.

## Rollback

If Qwen3-Embedding-4B underperforms or is unavailable:

1. Keep `nomic-embed-text` as default.
2. Keep Qwen3-Embedding-4B artifacts for analysis.
3. Do not delete Nomic artifacts or fallback configuration.
4. Re-run bakeoff after dimension, instruction, batching or residency changes.

## Machine-readable block

<!-- machine-readable: pkd-d2p-qwen3-4b-vs-nomic-v1 -->
```json
{
  "schema_version": "pkd-d2p-qwen3-4b-vs-nomic-v1",
  "decision_type": "D2P",
  "reversible": true,
  "candidates": [
    "nomic-embed-text",
    "Qwen/Qwen3-Embedding-4B"
  ],
  "qwen3_4b_dimensions": 2560,
  "python_rrf_default": true,
  "winner": null
}
```
