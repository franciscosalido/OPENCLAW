# RAG-01B PR-05B — LiteLLM Host Audit and Hardening

Status: Draft

Historical SDD note: the PR-05B host-audit contract was superseded by the
current host-only root wrapper contract (`./start_quimera.sh --start`,
`./start_quimera.sh --status`, `./start_quimera.sh --stop`) and by the
dedicated scripts in `infra/litellm/`. Do not use this historical file to
require reintroducing removed `start_quimera.sh` subcommands.

## Objetivo

Auditar e endurecer o LiteLLM como gateway local do host no QUIMERA/OpenClaw,
sem reintroduzir LiteLLM no Docker Compose e sem alterar HybridRAG,
PostgreSQL/TimescaleDB, Qdrant retrieval cache, MCP, FastAPI ou gRPC.

## Contexto

LiteLLM e o gateway canonico host para chamadas OpenAI-compatible locais. O
runtime local segue:

```text
Agentic / RAG callers -> LiteLLM host :4000 -> Ollama :11434
```

Docker Compose gerencia apenas PostgreSQL e Qdrant. Ollama e LiteLLM rodam no
host. Esta decisao respeita os ADRs local-first e o PKD de memory fabric: agentes
nao acessam bancos diretamente, e LiteLLM permanece gateway de entrada.

## Correcao

Nenhum container LiteLLM e permitido. O start padrao usa
`infra/litellm/start_litellm.sh`, que:

- faz bind em `127.0.0.1:4000`;
- exporta `LITELLM_MODE=PRODUCTION` e `LITELLM_LOG=ERROR`;
- usa `--num_workers 1`;
- reaproveita LiteLLM ja saudavel em `/health/readiness`;
- grava apenas PID proprio em `.runtime/litellm.pid`;
- aguarda readiness por ate 10s.

## Contratos RC-01..RC-24

RC-01: LiteLLM host-only, sem imagem/servico Docker.  
RC-02: aliases legados `local_chat`, `local_think`, `local_rag`, `local_json`,
`quimera_embed`, `local_embed` preservados.  
RC-03: cache LLM usa `quimera_llm_cache`.  
RC-04: cache LLM nunca colide com `quimera_query_cache`.  
RC-05: `similarity_threshold` em `(0, 1]`.  
RC-06: chat timeout `120`, stream timeout `45`.  
RC-07: embedding timeout `5`, stream timeout `5`.  
RC-08: `max_retries <= 2`.  
RC-09: `qdrant-semantic` e experimental e protegido por flag.  
RC-10: embedding do cache semantico e alias local.  
RC-11: dimensao canonica de embedding e `768`.  
RC-12: `request_timeout = 165`.  
RC-13: modelos usam `os.environ/OLLAMA_BASE_URL` ou loopback local.  
RC-14: modelos usam provider local Ollama.  
RC-15: logs seguros: JSON, verbose off, message logging off, redaction on.  
RC-16: `master_key` via `os.environ/LITELLM_MASTER_KEY`.  
RC-17: `timeout >= stream_timeout` em todos os modelos.  
RC-18: startup usa `/health/readiness`; `/health` fica opt-in.  
RC-19: start host exporta modo/log e usa host/porta/workers canonicos.  
RC-20: stop mata apenas PID proprio, SIGTERM e SIGKILL no mesmo PID.  
RC-21: `litellm-audit` gera JSON e Markdown locais.  
RC-22: audit inclui version fingerprint best-effort.  
RC-23: benchmark de overhead e opt-in.  
RC-24: eventos observaveis sao JSON local sem conteudo sensivel.

## Cache LLM vs Cache RAG

`quimera_llm_cache` pertence ao gateway LiteLLM. `quimera_query_cache` pertence
ao cache de retrieval do HybridRAG. As duas collections nunca devem ser
mescladas, apagadas ou recriadas por este PR.

## qdrant-semantic Experimental

O YAML fonte declara `type: qdrant-semantic`, mas o renderer so mantem esse
backend quando `QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL=1` e Qdrant esta
pronto em `http://127.0.0.1:6333`. Caso contrario, o runtime usa fallback
`local` ou `in-memory`.

Bug conhecido monitorado: `AttributeError: 'Cache' object has no attribute
'cache'` em alguns caminhos de Qdrant semantic cache. O fallback existe para
evitar derrubar o gateway por uma feature experimental.

O audit reporta RC-09 como `warn` quando o YAML fonte declara
`qdrant-semantic` mas a flag experimental nao esta ativa. Isso e
observabilidade intencional: o runtime continua valido porque o renderer aplica
fallback local.

## Timeout Policy

- Chat/Qwen: `timeout=120`, `stream_timeout=45`.
- Embeddings/Nomic: `timeout=5`, `stream_timeout=5`.
- Global: `request_timeout=165`.

`local_json` preserva `timeout=60` e `stream_timeout=45`. Pela documentacao do
LiteLLM, `timeout` limita a chamada completa e `stream_timeout` limita a espera
pelo primeiro chunk em streaming. O valor 45s e aceito por RC-17
(`45 <= 60`) e protege slow-start local, mas operadores devem preferir payloads
JSON concisos; contexto JSON longo pode exigir ajuste explicito de caller ou
alias futuro.

## Health Policy

LiteLLM documenta `/health/readiness` para readiness e `/health/liveliness` para
liveness. `/health` pode chamar modelos reais e fica restrito a smoke opt-in.

## Start/Stop Lifecycle

`scripts/start_quimera.sh litellm-start` delega para
`infra/litellm/start_litellm.sh`. `litellm-stop` para apenas `.runtime/litellm.pid`.
Nao ha `pkill`, `killall`, `down -v`, `docker volume rm` ou prune destrutivo.

## Audit Report

`python -m infra.litellm.audit` gera:

- `.runtime/reports/litellm_audit.json`
- `.runtime/reports/litellm_audit.md`

O relatorio contem RC status, cache policy, endpoints, version fingerprint e
seguranca host-only. Nao contem prompt bruto, respostas, chunks, vetores,
Authorization, API keys, DSN completo ou senhas.

## Version Fingerprint

`python -m infra.litellm.version_fingerprint` coleta best-effort:

- Python direto do runtime (`python`, `python_version`, `python_executable`),
  platform, LiteLLM, Pydantic, HTTPX e qdrant-client;
- Ollama `/api/version`;
- Qdrant `/readyz` e `/collections`;
- Docker Compose version;
- PostgreSQL/TimescaleDB quando DSN seguro estiver disponivel.

Falhas viram warnings estruturados.

## Proxy Overhead Benchmark

`python -m infra.litellm.overhead_benchmark` so executa benchmark real quando
`QUIMERA_LITELLM_BENCHMARK=1`. Sem opt-in retorna `status=SKIPPED_VALID` e
`skipped=true`. O budget diagnostico e `p95_overhead_ms < 50`.

## Regression Matrix

- Gateway/Agentic aliases continuam presentes.
- Agent0 regression e opt-in via `QUIMERA_AGENT0_GATEWAY_REGRESSION=1`.
- Qdrant cache smoke e opt-in e nunca deleta collections.
- Benchmark real e opt-in.
- Full unit suite deve permanecer independente de servicos vivos.

## Safe Events for PR-06

Eventos locais usam chaves OTel-friendly:

- `event.name`
- `service.name`
- `quimera.component`
- `quimera.stage`
- `status`
- `duration_ms`
- `error.type`
- `error.message_sanitized`
- `endpoint.kind`

## Test Plan

Rodar:

```bash
uv run pytest tests/unit/test_litellm_config_yaml.py tests/unit/test_litellm_timeout_policy.py tests/unit/test_litellm_config_validator.py tests/unit/test_litellm_cache_policy.py tests/unit/test_litellm_audit_contract.py tests/unit/test_litellm_version_fingerprint.py tests/unit/test_litellm_overhead_contract.py tests/unit/test_start_quimera_litellm_host.py tests/unit/test_start_quimera_script.py
uv run python -m infra.litellm.config_validator infra/litellm/litellm_config.yaml
uv run python -m infra.litellm.render_config
uv run python -m infra.litellm.audit
bash -n scripts/start_quimera.sh infra/litellm/start_litellm.sh
```

## Escopo Negativo

Nao implementar container LiteLLM, MCP server, FastAPI, gRPC, remote providers,
downloads de modelos, migrations, schema SQL, HybridRAG changes, Qlib/Kronos,
delecoes/recreates de collections Qdrant ou acesso a dados reais.

## Rollback

Reverter este PR restaura o contrato PR-05: LiteLLM host-only com validate,
render, start, stop e smoke. Nenhum volume Docker ou banco precisa ser alterado.

## Como Rodar

```bash
./scripts/start_quimera.sh litellm-validate
./scripts/start_quimera.sh litellm-render
./scripts/start_quimera.sh litellm-start
./scripts/start_quimera.sh litellm-smoke
./scripts/start_quimera.sh litellm-audit
./scripts/start_quimera.sh litellm-benchmark
```
