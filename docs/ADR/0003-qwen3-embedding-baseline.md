# ADR-0003 — Qwen3 Dense Embedding Baseline

## Status

Proposed.

## Contexto

O RAG-1A deve comparar `nomic_dense_v1` contra `qwen3_dense_8b_v1`
usando o mesmo corpus e as mesmas queries do benchmark financeiro brasileiro.

## Decisão

A decisão final deve ser gerada pelo runner do PR-04C e registrada nos
artefatos locais:

- `evaluation/results/dense_embedding_ab.json`
- `evaluation/results/dense_embedding_ab.md`
- esta ADR, atualizada pelo runner com `accepted_profile` e
  `promote_qwen3_dense`

## Critério

Qwen3 só pode ser promovido se passar simultaneamente pelos thresholds de
qualidade e latência definidos no gate do PR-04C.

## Fora de Escopo

- BM25 e hybrid search.
- Reranker.
- Agentic RAG e multi-tool orchestration.
- Alterar `active_profile` de produção neste PR.
