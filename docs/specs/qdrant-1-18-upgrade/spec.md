# Qdrant 1.18.0 Upgrade - Specification

Status: draft
Scope: Q18-01 docs-as-code only
Runtime changes: none

## Functional Requirements

FR-01: Documentar o upgrade Qdrant 1.13.x -> 1.18.0.

FR-02: Mapear features 1.18 relevantes para Quimera.

FR-03: Documentar diferencas 1.13.x vs 1.18.

FR-04: Preservar Python RRFFusion como fonte de verdade ate benchmark.

FR-05: Preparar collection benchmark futura, sem cria-la neste PR.

FR-06: Documentar escopo destrutivo local para PR futuro.

FR-07: Documentar por que PostgreSQL/pgvector fica fora deste ciclo.

FR-08: Definir gates para proximos PRs.

FR-09: Criar ADR preliminar.

FR-10: Criar indice de fontes oficiais Qdrant 1.18.

## Non-Functional Requirements

NFR-01: Local-first.

NFR-02: Async-friendly.

NFR-03: Memory-aware.

NFR-04: Benchmarkable.

NFR-05: Reproducible docs-as-code.

NFR-06: Agent-friendly.

NFR-07: No hidden destructive behavior.

NFR-08: Compatible with common agent memory files.

## Safety Requirements

SR-01: Nenhuma collection sera apagada neste PR.

SR-02: Nenhum Docker sera alterado neste PR.

SR-03: Nenhuma dependencia sera atualizada neste PR.

SR-04: Nenhum benchmark sera executado neste PR.

SR-05: Nenhum smoke live sera executado neste PR.

SR-06: Nenhuma decisao final de promocao sera tomada neste PR.

SR-07: PostgreSQL nao sera instalado neste PR.

## Feature Triage

### Use Now / likely in next PRs

- version reporting
- memory reporting para benchmark visibility
- strict mode evaluation, se validado em collection temporaria

### Research

- TurboQuant
- dynamic CPU pool
- low memory mode
- native Weighted RRF
- DBSF
- add/delete named vectors

### Do Not Use Yet

- destructive vector deletion outside benchmark collections
- TurboQuant as default
- native RRF as default
- PostgreSQL as RAG backend

## Future Acceptance Gates

Qdrant 1.18 may proceed only if:

- existing hybrid unit tests remain green
- PR-10 smoke works with temporary collections
- Recall@10 and NDCG@5 do not regress
- p95 latency does not exceed agreed multiplier
- memory reporting confirms expected footprint
- no protected collection is modified
- client/server versions are explicitly recorded
- rollback to the 1.13.x baseline is documented and rehearsable locally

## Out-of-Scope Runtime Surfaces

Q18-01 does not change:

- `pyproject.toml`
- `uv.lock`
- Docker image tags
- Docker Compose files
- Qdrant collection schemas
- backend RAG code
- scripts
- tests
- live Qdrant state
