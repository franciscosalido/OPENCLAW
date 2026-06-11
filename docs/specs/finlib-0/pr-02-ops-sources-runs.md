# FL-PR02 — Ops Sources and Ingestion Runs

Status: Implementation branch

Branch: `feat/finlib-ops-sources-runs`

## Objetivo

Criar o núcleo operacional mínimo para fontes financeiras e runs de ingestão do
FINLIB-0, sem criar agentes, repositories, outbox, watermarks ou tabelas de
auditoria.

Este PR adiciona somente a migration `019_create_ops_sources_runs.sql` com as
tabelas `ops_data_sources` e `ops_ingestion_runs`.

## Schema Diff

### `ops_data_sources`

- `source_id TEXT PRIMARY KEY`
- `kind TEXT NOT NULL`
- `base_url TEXT`
- `license_note TEXT`
- `methodology_limitations TEXT NOT NULL`
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

`source_id` é slug-like, aceita minúsculas, números, `_`, `-`, `.`, `:` e tem
limite operacional de 128 caracteres. A limitação metodológica é dado
obrigatório para evitar conhecimento tribal e precisa conter pelo menos um
caractere não-whitespace.

### `ops_ingestion_runs`

- `run_id UUID PRIMARY KEY DEFAULT uuidv7()`
- `source_id TEXT NOT NULL REFERENCES ops_data_sources(source_id)`
- `agent_id TEXT NOT NULL`
- `mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'execute'))`
- `status TEXT NOT NULL CHECK (status IN ('created', 'running', 'completed',
  'failed', 'cancelled'))`
- `started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `finished_at TIMESTAMPTZ`
- counters não negativos
- `source_snapshot_hash TEXT`
- `error_summary TEXT`
- `trace_id UUID NOT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Para `mode='execute' AND status='completed'`, `source_snapshot_hash` é
obrigatório e precisa conter pelo menos um caractere não-whitespace. `dry_run`
pode existir sem snapshot hash.

Campos textuais semanticamente obrigatórios usam regex PostgreSQL `~ '\S'` em
vez de `btrim()` para rejeitar valores compostos apenas por espaço, tab,
newline ou carriage return.

## Seed B3

A fonte `b3_cotacoes_historicas` é gravada como dado em
`ops_data_sources`. A limitação registrada é que a série histórica da B3 não é
ajustada por inflação nem por proventos corporativos, portanto deve ser usada
com cuidado em retorno total, backtests e comparações históricas.

## Índices

- `ops_ingestion_runs(source_id, started_at DESC)`
- `ops_ingestion_runs(trace_id)`
- `ops_ingestion_runs(status, started_at DESC)`

## Fora de Escopo

- `ops_ingestion_watermarks`
- `ops_data_quality_checks`
- `ops_outbox_events`
- `audit_agent_writes`
- repositories
- data agents
- MCP tools
- runtime A2A

## Validação Esperada

```bash
uv run pytest tests/unit/test_finlib_ops_sources_runs_schema.py -q
uv run pytest tests/integration/test_finlib_ops_sources_runs_live.py -q
```
