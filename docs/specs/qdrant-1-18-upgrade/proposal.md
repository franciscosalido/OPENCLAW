# Qdrant 1.18.0 Upgrade - Proposal

Status: draft
Relacionado: RAG-1A, Q18-01..Q18-07
Owner: Quimera Agentic RAG Team
Documento: docs-as-code / SDD lightweight
Snapshot date: 2026-05-23

## Objetivo

Avaliar Qdrant 1.18.0 para o Quimera, antes de qualquer mudanca de runtime,
Docker, dependency pin, schema ou collection.

O foco do mini-sprint Q18 e mapear se as seguintes capacidades podem melhorar o
RAG local-first construido no RAG-1A:

- named vectors create/delete API
- TurboQuantization
- low memory mode
- strict mode
- deep memory reporting
- dynamic CPU pool
- audit/tracing improvements
- hybrid dense+sparse+RRF

## Contexto

- RAG-1A estabeleceu Hybrid RAG dense+sparse+Weighted RRF.
- Qdrant 1.13.x e o baseline historico do projeto.
- O sistema ainda nao esta em producao.
- Collections antigas locais podem ser apagadas em PR futuro, mas nao neste PR.
- PostgreSQL/pgvector e alternativa futura, nao alvo deste mini-sprint.

Historicamente, este repositorio fixava `qdrant-client==1.13.2` em
`pyproject.toml`. O contrato ativo agora exige `qdrant-client>=1.18`.

## Hipotese

Qdrant 1.18 pode melhorar desempenho, footprint de memoria, evolucao de schema
e observabilidade do Quimera local-first multiagente.

## Null Hypothesis

Qdrant 1.18 nao oferece melhoria mensuravel em recall, latencia ou footprint
que justifique o custo de upgrade frente ao baseline 1.13.x.

## Decisao preliminar

Avaliar Qdrant 1.18 agora.

Adiar PostgreSQL/pgvector para uma fase posterior, caso surja necessidade
relacional, ACID, multi-tenant SQL ou GraphRAG que justifique um novo backend.

## Non-goals

- No dependency bump in this PR.
- No Docker image change.
- No Qdrant collection mutation.
- No migration of real data.
- No benchmark execution.
- No production migration.
- No PostgreSQL install.
- No GraphRAG implementation.
- No change to Python RRFFusion as source of truth.

## Contrato destrutivo local

Este PR nao permite reset destrutivo. Ele apenas documenta o contrato para PRs
futuros, que deverao implementar guards explicitos, revisaveis e testados.

Allowed destructive targets for future PRs:

- `q18_benchmark_*`
- `q18_smoke_*`
- `quimera_knowledge_v2_dev_*`

Forbidden:

- `quimera_knowledge`
- `quimera_knowledge_v2`
- any non-prefixed collection
- any remote Qdrant host

Pseudo-comando ilustrativo, nao executavel neste PR:

```text
# future-only, guarded by Q18-03 tests and human approval:
# q18 reset --collection q18_benchmark_<id> --local-only --confirm-prefix
```

## Proximos PRs

- Q18-02 - Qdrant 1.18 Server/Client Upgrade
- Q18-03 - Destructive Local Reset + Collection Governance
- Q18-04 - Qdrant 1.18 Hybrid Schema Refactor
- Q18-05 - Local-First Qdrant Performance Tuning Profiles
- Q18-06 - Python RRF vs Qdrant Native Weighted RRF Adapter
- Q18-07 - Benchmark, Comparison Report + ADR Decision

## Acceptance Criteria

- `proposal.md`, `spec.md`, `design.md`, `tasks.md`, research notes, vendor
  docs index and ADR exist.
- Decision "Qdrant 1.18 now, PostgreSQL later" is documented as preliminary.
- Relevant Qdrant 1.18 features are mapped to Quimera use cases.
- Risks and local rollback are documented.
- The PR is docs-only.
- No Docker, dependency, schema, code or collection mutation is made.
