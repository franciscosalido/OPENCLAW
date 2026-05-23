# Q18 Local Reset Policy

## Scope

Este reset é apenas para ambiente local de desenvolvimento/benchmark.

Q18-03 cria governanca destrutiva controlada. Ele nao cria schema hibrido, nao
configura named vectors, nao faz ingestao, nao roda benchmark e nao toca Qdrant
remoto.

## Required gates

- host `localhost`, `127.0.0.1` ou `::1`
- `QDRANT_LOCAL_RESET=1`
- `--i-understand-this-deletes-local-qdrant-collections`
- `--execute`

## Dry-run gates

Dry-run requires only a local host. `QDRANT_LOCAL_RESET=1` and
`--i-understand-this-deletes-local-qdrant-collections` are NOT required for
dry-run. No collection is deleted or created.

## Default behavior

Dry-run.

Sem `--execute`, o script deve listar o plano e retornar JSON seguro, sem
deletar ou criar collections.

## Allowed targets

Exact names:

- `openclaw_knowledge`
- `quimera_knowledge`
- `quimera_knowledge_v2`

Allowed prefixes:

- `q18_benchmark_`
- `q18_smoke_`
- `quimera_benchmark_`
- `quimera_hybrid_smoke_`
- `gw07_synthetic_rag_`

Esses nomes sao permitidos somente porque o ambiente ainda nao esta em producao
e apenas com as gates destrutivas acima.

## Forbidden

- remote hosts
- cloud URLs
- wildcard deletion
- substring deletion
- deletion by arbitrary collection name
- production/staging
- Qdrant Cloud
- schema mutation
- payload inspection
- vector inspection
- recreate of `quimera_knowledge`
- recreate of `quimera_knowledge_v2`

## Examples

Dry-run:

```bash
uv run python scripts/qdrant_reset_local_collections.py --host localhost
```

Execute local:

```bash
QDRANT_LOCAL_RESET=1 uv run python scripts/qdrant_reset_local_collections.py \
  --host localhost \
  --execute \
  --i-understand-this-deletes-local-qdrant-collections
```

Execute + benchmark placeholder:

```bash
QDRANT_LOCAL_RESET=1 uv run python scripts/qdrant_reset_local_collections.py \
  --host localhost \
  --execute \
  --i-understand-this-deletes-local-qdrant-collections \
  --recreate-benchmark \
  --benchmark-collection q18_benchmark_hybrid_local
```

Note: Q18-03 exposes the benchmark recreation flag and protocol, but the real
adapter refuses schema creation until Q18-04 owns the benchmark schema.

## Rollback

Re-run ingest/smoke/benchmark from source corpus.

Do not restore from unknown old collection state.
