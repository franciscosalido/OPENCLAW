# RAG-01B-PR-03 - HybridRAG Semantic Cache Layer (Qdrant)

## Objetivo

Criar uma camada assíncrona de cache semântico para resultados de retrieval do
HybridRAG, usando Qdrant em uma coleção separada da coleção de conhecimento.

Este PR cria apenas uma camada plugável. Ele não altera o pipeline HybridRAG
principal.

## Contexto

Qdrant continua sendo a memória vetorial do QUIMERA. PostgreSQL 18.4 +
TimescaleDB guarda memória temporal estruturada. A coleção de cache é separada
da coleção de conhecimento para evitar mistura entre conteúdo canônico e
resultados derivados de retrieval.

## Decisão: retrieval cache, não response cache

O cache armazena:

- vetor já calculado da query;
- ids de documentos recuperados;
- scores;
- metadados seguros;
- fingerprint do perfil de retrieval.

O cache não armazena query bruta, prompt bruto, resposta final do LLM, chunks
inteiros, embeddings no payload ou secrets.

## Qdrant collection separada

Default: `quimera_query_cache`.

Coleção de conhecimento e coleção de cache devem permanecer separadas. A
camada nunca usa `recreate_collection`, nunca apaga coleção inteira e nunca
recria coleção incompatível automaticamente.

## Cache fingerprint

O fingerprint amarra cache a:

- profile name;
- embedding model;
- embedding dimension;
- source collection;
- corpus epoch;
- retrieval fingerprint;
- schema version.

## Payload permitido

- `result_doc_ids`
- `result_scores`
- `fusion_backend`
- `profile_name`
- `embedding_model`
- `embedding_dim`
- `source_collection`
- `corpus_epoch`
- `retrieval_fingerprint`
- `schema_version`
- `created_at`
- `expires_at`
- `hit_count`
- `metadata` sanitizada

## Payload proibido

Não armazenar query bruta, prompt, resposta, chunks, chunk text, secrets, API
keys, tokens, embeddings ou vectors no payload.

## Settings/env vars

Configuração via `CacheSettings` com prefixo `QUIMERA_CACHE_`. O PR usa injeção
explícita de settings no `CacheLayer`.

## Contratos Python

Modelos imutáveis:

- `CacheFingerprint`
- `RetrievalResult`
- `CacheEntry`
- `CacheHit`
- `CacheInvalidationResult`

## CacheLayer semantics

`lookup` retorna `CacheHit | None`. `store` retorna `CacheEntry | None`; quando
cache está desabilitado, retorna `None` sem chamar Qdrant.

## Collection management

`CacheCollectionManager` cria a collection quando ausente, valida dimensão e
distância quando existente e cria payload indexes idempotentes.

## Invalidation strategy

Invalidation é sempre por filtro restritivo: schema version, fingerprint,
corpus epoch ou expiração. Dry-run conta sem deletar.

## Test plan

Unitários usam `FakeQdrantClient`. Integrações rodam apenas com
`TEST_QDRANT_URL` ou `QUIMERA_QDRANT_URL` e usam collection temporária
`quimera_query_cache_test_<uuid>`.

## Security/privacy

Sem query bruta, prompt, chunks inteiros, resposta final, secrets, API keys ou
tokens. Exceções devem ser úteis sem despejar payload bruto.

## Escopo negativo

Sem geração de embeddings, LLM call, RRF, reranker, MCP, API, gRPC,
PostgreSQL, TimescaleDB, Qlib, Kronos, response cache, prompt cache ou
mutation da knowledge collection.

## PRs futuros

- Integrar seam no pipeline HybridRAG principal.
- Adicionar métricas/observabilidade segura.
- Avaliar políticas de TTL/hot cache em produção local.
