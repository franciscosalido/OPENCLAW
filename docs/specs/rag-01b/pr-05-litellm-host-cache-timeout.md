# RAG-01B PR-05 — LiteLLM Host Cache + Timeout Hardening

Status: Draft

Superseded operational hardening: see
`docs/specs/rag-01b/pr-05b-litellm-host-audit.md` for audit reports, version
fingerprint, opt-in overhead benchmark and RC-01..RC-24 host boundary checks.

## Decisao

LiteLLM e um processo Python local do host. Docker Compose nao gerencia LiteLLM no QUIMERA. O Compose gerencia apenas Postgres e Qdrant. O start_quimera.sh reaproveita um LiteLLM ja rodando ou inicia exatamente um processo host controlado por PID.

## Escopo

- Remover LiteLLM do Compose local.
- Manter Postgres e Qdrant no Docker.
- Manter os aliases canonicos do Gateway:
  - local_chat
  - local_think
  - local_rag
  - local_json
  - quimera_embed
  - local_embed
- Validar `infra/litellm/litellm_config.yaml` antes de iniciar o gateway host.
- Renderizar `infra/litellm/generated/litellm_config.runtime.yaml` como artefato local nao versionado.
- Usar cache semantico Qdrant apenas quando habilitado explicitamente e Qdrant responder; caso contrario, renderizar fallback `local`.

## Contrato De Runtime

- Host: `127.0.0.1`
- Porta: `4000`
- Readiness: `/health/readiness`
- Liveliness: `/health/liveliness`
- Model listing: `/v1/models`
- O probe padrao nao usa `/health`, pois esse endpoint pode chamar modelos reais.

## Comandos

`scripts/start_quimera.sh` deve expor:

- `litellm-validate`
- `litellm-render`
- `litellm-start`
- `litellm-stop`
- `litellm-restart`
- `litellm-smoke`

`litellm-start` deve reaproveitar um processo ja pronto em `127.0.0.1:4000`.
Quando iniciar um processo novo, deve gravar apenas `.runtime/litellm.pid`.

`litellm-stop` deve encerrar somente o PID gravado pelo proprio script. Nao usar
`pkill`, `killall` ou encerramento por nome de processo.
Se o processo proprio nao encerrar apos SIGTERM, o script pode usar SIGKILL
apenas no PID gravado em `.runtime/litellm.pid`.

## Cache

O arquivo fonte pode declarar:

- `type: qdrant-semantic`
- `qdrant_api_base: os.environ/QDRANT_API_BASE`
- `qdrant_collection_name: quimera_llm_cache`
- `qdrant_semantic_cache_embedding_model: quimera_embed`
- `qdrant_semantic_cache_vector_size: 768`
- `similarity_threshold: 0.92`

A dimensao canonica atual do embedding e 768 para `nomic-embed-text`, exposta
no validador como `CANONICAL_EMBED_DIM`.

O renderizador so mantem `qdrant-semantic` quando:

- `QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL=1`
- Qdrant responde em `QDRANT_API_BASE`

Sem isso, o runtime renderizado usa cache local quando
`QUIMERA_LITELLM_CACHE_FALLBACK=local` ou quando o fallback nao e informado.

## Escopo Negativo

- Nao criar container LiteLLM.
- Nao mapear porta 4000 no Compose.
- Nao adicionar provider remoto.
- Nao adicionar OpenAI, Anthropic, Google, Azure, torch, transformers,
  langchain, llama_index, FastAPI, gRPC ou MCP.
- Nao ler nem versionar `.env` ou `.env.local`.
