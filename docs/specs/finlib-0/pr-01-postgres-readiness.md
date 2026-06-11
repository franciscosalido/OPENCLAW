# FL-PR01 — PostgreSQL/TimescaleDB Readiness

Status: Implementation branch

Branch: `feat/finlib-postgres-readiness`

## Objetivo

Criar o primeiro gate executável do FINLIB-0 para confirmar que a memória
relacional-temporal canônica está pronta antes de qualquer agente financeiro
rodar.

O gate valida PostgreSQL 18.4, TimescaleDB, pgvector, `pgcrypto`, `pg_trgm`,
`btree_gin`, `pg_stat_statements`, head de migrations, escrita temporária e
presença de role read-only.

## Escopo

- Adicionar migration `018_enable_library_extensions.sql`.
- Criar `scripts/check_postgres_readiness.py`.
- Integrar um resumo seguro ao `scripts/quimera_status.py`.
- Adicionar testes unitários offline e teste live em banco isolado.

## Contrato JSON

`scripts/check_postgres_readiness.py --json` emite somente campos `ok` ou
`fail`:

- `postgres`
- `database`
- `timescaledb`
- `vector`
- `pgcrypto`
- `pg_trgm`
- `btree_gin`
- `pg_stat_statements`
- `migration_head`
- `write_test`
- `readonly_role`

Exit code `0` significa todos os campos `ok`. Exit code `1` significa pelo
menos uma condição crítica ausente.

O relatório não inclui DSN, host, senha, traceback, query text ou payload.

## Gate de agentes

Nenhum data agent FINLIB deve iniciar ingestão, curadoria, escrita de features
ou rotinas de Tesouro MtM enquanto o readiness PostgreSQL/FINLIB não retornar
exit code `0`.

O gate final consolidado `scripts/check_finlib_readiness.py` fica para PR
posterior. Até lá, FL-PR01 usa `scripts/check_postgres_readiness.py` como gate
operacional inicial.

## Decisões

- `ltree` permanece fora deste PR porque ainda não há consumidor de taxonomia.
- O script não cria roles. Ele apenas verifica a presença da role configurada.
- A role esperada é configurável por `QUIMERA_POSTGRES_READONLY_ROLE`; o default
  local é `quimera_readonly`.
- Volumes novos criam `quimera_readonly NOLOGIN` via
  `infra/postgres/initdb/002_readonly_role.sql`. Volumes antigos devem aplicar
  esse mesmo bootstrap uma vez antes de exigir readiness verde.
- O bootstrap também aplica default privileges para `FOR ROLE quimera`, porque
  as migrations locais criam tabelas com esse role.
- A migration runner continua sendo a fonte de verdade de schema.
- `pg_stat_statements` é pré-carregado pelo compose local com
  `shared_preload_libraries=timescaledb,pg_stat_statements`; a migration 018
  não altera configuração de servidor. Volumes antigos podem precisar de
  `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` no banco `quimera`.

## Validação Esperada

```bash
uv run pytest tests/unit/test_postgres_readiness_script.py tests/unit/test_postgres_migrations_static.py -q
```

Com Postgres live:

```bash
uv run pytest tests/integration/test_postgres_readiness_live.py -q
```
