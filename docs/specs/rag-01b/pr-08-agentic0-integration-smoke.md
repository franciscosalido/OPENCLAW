# RAG-01B PR-08 - Agentic0 End-to-End System Integration Smoke

Status: Draft implementation

Historical SDD note: the former `agentic0-smoke` `start_quimera.sh` subcommand
reference was superseded by the current host-only root wrapper contract
(`./start_quimera.sh --start`, `./start_quimera.sh --status`,
`./start_quimera.sh --stop`) and by `integration.run_agentic0_smoke_test`.
Do not use this historical file to require reintroducing removed
`start_quimera.sh` subcommands.

## Objetivo

O PR-08 fecha o sprint RAG-01B com um System Integration Gate local-first.

O PR-08 não prova inteligência geral do agente. Ele prova integração sistêmica:
Agentic0 consegue usar o LiteLLM como único gateway para modelo, memória
relacional e memória vetorial, com MCP tools locais, HybridRAG sintético, OTel
seguro e resposta final auditável.

## Arquitetura do System Integration Gate

Agentic0 runtime chama somente o LiteLLM host em `http://127.0.0.1:4000`.
Postgres, Qdrant e Ollama permanecem atrás de gateway, repository, MCP ou
fixtures de setup/validação.

## Regra Principal

Agentic0 fala somente com LiteLLM. O client runtime não importa `asyncpg`, não
importa `qdrant_client`, não lê DSN e não chama Ollama ou Qdrant diretamente.

## LiteLLM Host-Only

LiteLLM continua fora do Docker. O PR-08 não cria segundo LiteLLM e não habilita
provider remoto.

## MCP Postgres e MCP Qdrant via LiteLLM

`quimera_postgres_memory` e `quimera_qdrant_memory` são registrados em
`infra/litellm/litellm_config.yaml` com transporte `http` e loopback. Se a versão
local do LiteLLM não expuser introspection MCP, o healthcheck marca
`gateway_introspection_skipped=true` e mantém validação estática.

## Deterministic Smoke vs Autonomous Tool-Use Smoke

O deterministic smoke é obrigatório e seguro. Autonomous tool-use é opt-in via
`QUIMERA_AGENTIC0_AUTONOMOUS_TOOLS=1` e não é hard gate.

## Qdrant HybridRAG Dense+Sparse

A fixture PR-08 usa coleção sintética `quimera_pr08_hybrid_smoke_<run_id>`,
vetores `text-dense` e `text-sparse`, e RRF determinístico.

O Recall@5 reportado pela fixture é evidência determinística offline, não
qualidade live do modelo `nomic-embed-text`. O artefato deve marcar
`quality_mode=offline_synthetic_fixture`, `live_quality_checked=false` e
`live_quality_required=true` até a stack completa validar Qdrant HybridRAG com
o encoder local vivo.

## Postgres Memory Context

O smoke valida o contrato de sessão e estado via MCP/health. Writes reais são
controlados por `QUIMERA_AGENTIC0_WRITE_SMOKE=1`.

## Agentic0 Scenario

O cenário cria run id, correlation id, consulta health integrado, valida
HybridRAG sintético, chama tools permitidas e faz síntese curta via LiteLLM.

## Healthcheck Único

`python -m integration.check_integration_health --json` retorna JSON puro com
Ollama, LiteLLM, Qdrant, Postgres, MCP, modelos e OTel.

## allowed_tools e virtual keys

Agentic0 usa lista explícita de tools. Wildcard, admin e destructive tools são
proibidos. A política mínima `agentic0-smoke` é documentada e validada
estaticamente.

## OTel Spans Esperados

Spans esperados: `agentic0.smoke`, `integration.health`, `litellm.chat`,
`mcp.postgres.tool`, `mcp.qdrant.tool`, `qdrant.hybrid_query` e
`postgres.memory_context`.

## Segurança, PII e Nível 0

Nível 0 nunca sai da máquina. Artefatos não devem conter prompt, resposta,
chunk, vetor, payload bruto, DSN ou segredo.

## Degradação Controlada

Serviços ausentes geram `fail`, `degraded` ou `skipped` explícito. O smoke
determinístico não faz retry infinito e não usa bypass direto.

## Latency Budget End-to-End

O relatório mede `total_ms`, `mcp_ms` e `llm_ms`. O p95 só é preenchido quando
a stack essencial está online. Sem stack live, o artefato deve marcar
`measurement_mode=degraded_no_live_stack`, `sample_count=0` e
`p95_warning=not_measured_stack_unavailable`. Quando a stack está online,
qualquer `p95_ms > 500` deve gerar `p95_warning=p95_exceeds_500ms`.

## LLM Harness Methodology

O PR-08 segue harness versionado, live calls opt-in, fixtures determinísticas,
logs padronizados e LLM-as-judge apenas diagnóstico.

## Artefatos Gerados

- `evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json`
- `evaluation/results/rag_01b_pr08_integration_health.json`
- `evaluation/results/rag_01b_pr08_latency_summary.json`
- `docs/rag/rag_01b_pr08_integration_report.md`

## Como Rodar

- `./scripts/start_quimera.sh integration-health --json`
- `./scripts/start_quimera.sh agentic0-smoke --json`
- `./scripts/start_quimera.sh pr08-report`
- `./scripts/start_quimera.sh rag01b-final-gate --json`

## Critérios de Aceite

Unit tests passam, integrações pulam limpo sem stack, Agentic0 runtime não usa
atalhos diretos, health JSON parseia, allowed_tools é explícito, e reports são
seguros.

## Escopo Negativo

Sem LiteLLM Docker, provider remoto, novo schema Postgres, migration, reindex
real, Kronos runtime, Qlib export real, LlamaIndex/LangChain obrigatório ou
LLM-as-judge como gate.

## Handoff PR-09

Multi-agent policy, autonomous tool-use hardening, KRONOS, evaluation harness
completo e shadow mode ficam para PR-09+.
