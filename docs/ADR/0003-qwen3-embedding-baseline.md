# ADR-0003 — Qwen3 Dense Embedding Baseline

## Status

**Inconclusive — Qwen3 embedding model not yet installed locally (2026-05-24)**

## Contexto

O benchmark Q18 deve comparar `nomic-embed-text` (768d) contra
`Qwen/Qwen3-Embedding-0.6B` (1024d) usando o mesmo corpus, as mesmas queries
e o mesmo schema de collection do benchmark financeiro brasileiro.

O benchmark anterior (Q18-07) usou exclusivamente `nomic-embed-text`.
Esta ADR governa a migração para Qwen3 como embedding padrão.

## Embedding Target

| Campo | Valor |
|---|---|
| Model | `Qwen/Qwen3-Embedding-0.6B` |
| Dimensions | 1024 |
| Provider | ollama (local) |
| Collection | `quimera_benchmark_hybrid_118_qwen3` |
| Query instruction | `"Given a financial advisory retrieval query in Portuguese, retrieve relevant passages from the Quimera financial knowledge base."` |
| Query instruction applied | Query side only (documents sem instrução) |

## Disponibilidade Atual

Qwen3-Embedding-0.6B não está instalado no Ollama local (2026-05-24).
Probe retorna `error: http_404`. Nomic continua como modelo operacional.

Para instalar: `ollama pull Qwen/Qwen3-Embedding-0.6B`

## Decisão

**Decisão atual:** `qwen3_inconclusive_missing_baseline`

Qwen3 não pode ser promovido sem evidência empírica de Recall@10, NDCG@5,
P50 e P95 comparáveis ou superiores ao Nomic no Qdrant 1.18.

A decisão será atualizada quando:

1. `ollama pull Qwen/Qwen3-Embedding-0.6B` completar com sucesso.
2. `evaluation/probe_embedding_model.py` retornar `available: true, dimensions: 1024`.
3. Todos os perfis `qdrant_118_qwen3_*` forem executados e seus artefatos gerados.
4. O comparador `compare_qdrant_113_vs_118.py` processar o cenário `qdrant_118_nomic_vs_qwen3_embedding`.

## Artefatos

| Artefato | Status |
|---|---|
| `evaluation/results/qdrant_118_qwen3_benchmark_summary.json` | ✅ Inconclusive gerado |
| `evaluation/results/qdrant_113_qwen3_baseline_missing.json` | ✅ Missing documentado |
| `evaluation/results/qdrant_118_qwen3_python_rrf.json` | ❌ Pendente (Qwen3 indisponível) |
| `docs/rag/qdrant_118_qwen3_upgrade_results.md` | ✅ Gerado (inconclusive) |

## Critério de Promoção

Qwen3 só pode ser promovido como embedding padrão se:

- NDCG@5 ≥ Nomic NDCG@5 (sem regressão de qualidade).
- Recall@10 ≥ Nomic Recall@10.
- P95 ≤ Nomic P95 × 1.2 (latência aceitável com vetores maiores).
- Sem regressão em qualquer cenário individual Qwen3.

## Decisões Possíveis

- `accept_qwen3_as_embedding_default` — Qwen3 supera ou empata Nomic em todas as métricas.
- `keep_nomic_temporarily` — Qwen3 mostra regressão; Nomic permanece padrão.
- `qwen3_inconclusive_missing_baseline` — **ESTADO ATUAL** — dados insuficientes.
- `defer_qwen3_due_to_regression` — Qwen3 falhou nos critérios de qualidade.

## Fora de Escopo

- Reranker.
- Agentic RAG e multi-tool orchestration.
- Alterar `active_profile` de produção sem evidência empírica.
- BM25 standalone (já coberto por hybrid RRF).

## Referências

- [docs/rag/qdrant_118_qwen3_upgrade_results.md](../rag/qdrant_118_qwen3_upgrade_results.md)
- [evaluation/probe_embedding_model.py](../../evaluation/probe_embedding_model.py)
- [ADR-018: Qdrant 1.18 Upgrade](ADR-018-qdrant-118-upgrade.md)
