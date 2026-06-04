# RAG-01B-PR-04 - Ollama Tuning + Keep-Alive Hardening

## Objetivo

Consolidar o controle local do QUIMERA em `scripts/start_quimera.sh`, com
Docker para PostgreSQL/Qdrant/LiteLLM e Ollama preferencialmente no host local.

## Problema

O runtime local tinha caminhos separados para Postgres, Qdrant, LiteLLM e
Ollama. Isso dificultava diagnosticar se os serviços estavam visíveis e
consistentes no Docker Desktop e no host.

## Decisão

`scripts/start_quimera.sh` é o controlador local único para start, stop,
restart, status, logs, doctor, test, warmup e release.

## Ollama Keep-Alive Policy

Ollama roda no host. O PR usa `OLLAMA_KEEP_ALIVE=-1` por padrão para manter os
modelos aquecidos. A API local também recebe `keep_alive` explicitamente nos
requests de warmup/release.

## Warmup Policy

`infra/ollama/warmup.py` aquece:

- `nomic-embed-text:latest` via `/api/embed`;
- `qwen3:14b` via `/api/chat`.

## Shutdown/Release Policy

`infra/ollama/shutdown_hook.py` descarrega modelos apenas quando solicitado com
`release` ou `stop --release-models`. Todos os requests de release usam
`keep_alive=0`.

## Docker Services Managed

- `postgres-memory` -> `quimera-postgres-memory`
- `qdrant` -> `quimera-qdrant`
- `litellm` -> `quimera-litellm`

## Healthchecks

Postgres usa `pg_isready`; Qdrant usa `/healthz`; LiteLLM usa
`/health/readiness`; Ollama usa `/api/version`.

## Commands

| Comando | Descricao |
| --- | --- |
| `start` | Sobe Docker local, verifica Ollama e aceita `--warmup`/`--doctor`. |
| `stop` | Para Docker local e somente o Ollama iniciado pelo script. |
| `restart` | Executa stop com release e start com build/warmup/doctor. |
| `status` | Mostra status dos servicos locais. |
| `logs` | Segue logs do Docker Compose local. |
| `doctor` | Executa checks de runtime local. |
| `test` | Roda testes unitarios relevantes e, opcionalmente, integracao. |
| `warmup` | Aquece modelos Ollama. |
| `release` | Descarrega modelos Ollama via `keep_alive=0`. |

`stop` nao apaga volumes. `stop --release-models` descarrega modelos. O caminho
recomendado apos merge e `restart --warmup --doctor`. `down -v` e proibido no
script padrao.

Reset de volume e uma operacao manual e explicita. `restart` preserva volumes
porque chama `docker compose down` sem `-v`; isso evita perda acidental de
memoria local. Se um operador suspeitar de dados corrompidos em volume local,
deve parar a stack e remover manualmente somente o volume pretendido com
`docker volume rm`, conforme `infra/README.md`.

## Tests

Unitarios cobrem config, contratos HTTP de warmup/release e leitura estatica do
script. Integracoes sao opt-in/skip-clean para Ollama e Docker indisponiveis.

## Security

Sem API externa, sem secrets hardcoded e sem download automatico obrigatorio de
modelos grandes. O script nao mata processos Ollama externos.

`LITELLM_MASTER_KEY` e obrigatorio. O compose usa interpolacao requerida de
Docker Compose para falhar cedo se a variavel nao estiver definida. Um exemplo
local nao secreto existe em `.env.local.example`.

## Escopo Negativo

Sem schema SQL novo, migrations de memoria, HybridRAG cache, MCP, API, gRPC,
Kronos, Qlib, pgvector logic, retrieval pipeline ou performance tests.

## Troubleshooting

- Se o warmup falhar por modelo ausente, rode `ollama pull <model>`.
- Se LiteLLM nao subir, verifique `docker compose logs litellm`.
- Se Postgres falhar por senha ausente, crie o arquivo local nao versionado em
  `infra/postgres/secrets/postgres_password.txt`.
