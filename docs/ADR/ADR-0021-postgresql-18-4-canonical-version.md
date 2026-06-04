# ADR-0021 - PostgreSQL 18.4 e a versao canonica do QUIMERA

## Status

Accepted

## Decisao

O QUIMERA / OPENCLAW adota PostgreSQL 18.4 como versao canonica para a
infraestrutura de memoria relacional-temporal.

A partir deste ADR:

- Toda documentacao ativa deve referenciar PostgreSQL 18.4.
- Docker Compose deve usar tag fixa `postgres:18.4-trixie`.
- Nao usar `postgres:latest`.
- Nao usar `postgres:18` sem minor pin.
- Nao usar PostgreSQL 16 em docs ativas, exceto quando explicitamente marcado
  como historico.
- O path de volume deve respeitar PostgreSQL 18+:
  - volume montado em `/var/lib/postgresql`;
  - `PGDATA` interno em `/var/lib/postgresql/18/docker`.
- RAG-01B PR-01 deve assumir PostgreSQL 18.4 como target.
- `asyncpg` continua sendo o driver Python.
- ORM pesado continua proibido.

`postgres:18.4-trixie` e a base operacional aprovada pelo time para o container
local. PostgreSQL 16 era referencia anterior do blueprint; foi superseded por
ADR-0021.

## Contexto

PostgreSQL 18.4 foi publicado oficialmente em 2026-05-14 e e a versao minor
corrente da linha PostgreSQL 18.

Este ADR existe para remover ambiguidade do projeto e substituir referencias
antigas a PostgreSQL 16 no SDD RAG-01B.

## Consequencias

- Infra local, compose e documentacao devem ser alinhados para PostgreSQL 18.4.
- Scripts que assumem `/var/lib/postgresql/data` precisam ser revisados.
- Migrations SQL do RAG-01B devem ser compativeis com PostgreSQL 18.4.
- Extensoes futuras como pgvector, TimescaleDB e Kronos devem respeitar esta
  base.
- Qualquer incompatibilidade futura deve ser tratada como issue de
  implementacao, nao como reabertura da decisao.

## Escopo negativo

Este ADR nao executa benchmark.

Este ADR nao compara PostgreSQL 16, 17, 18 ou 19.

Este ADR nao discute PostgreSQL 19 Beta.

Este ADR nao altera schema SQL.

Este ADR nao cria migration.

Este ADR nao cria teste.

Este ADR nao altera runtime, exceto referencias obvias em docs e configuracao
local alinhadas ao PR documental.

## Addendum - TimescaleDB e memoria temporal unificada

PostgreSQL 18.4 e a base canonica da memoria relacional-temporal do QUIMERA.

TimescaleDB e adotada como extensao temporal oficial sobre PostgreSQL, nao como
banco separado. A versao de TimescaleDB usada pela infraestrutura deve ser
compativel com PostgreSQL 18. TimescaleDB 2.23 introduziu compatibilidade
completa com PostgreSQL 18.

A partir deste ADR:

- PostgreSQL 18.4 + TimescaleDB compoem uma unica unidade logica de memoria
  temporal.
- Qlib nao e fonte de verdade.
- Diretorios Qlib, arquivos `.bin`, CSV ou Parquet sao artefatos derivados e
  descartaveis.
- Kronos nao tera memoria persistente separada.
- Entradas Kronos e datasets Qlib devem ser projecoes da memoria canonica
  PostgreSQL/TimescaleDB.
- Saidas Kronos devem retornar para PostgreSQL/TimescaleDB em tabelas
  versionadas de forecast/model run.
- Nenhum agente acessa Qlib, arquivo `.bin`, PostgreSQL ou Qdrant diretamente;
  agentes acessam a memoria por repository/API/MCP em PRs futuros.

ADR-0022 detalha a memoria temporal unica para TimescaleDB, Qlib e Kronos.

Referencia TimescaleDB 2.23.0:
<https://github.com/timescale/timescaledb/releases/tag/2.23.0>
