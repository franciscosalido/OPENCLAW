# ADR-0022 - Memoria Temporal Unica para TimescaleDB, Qlib e Kronos

## Status

Accepted

## Decisao

O QUIMERA adota PostgreSQL 18.4 + TimescaleDB como fonte unica de verdade para
memoria temporal de longo prazo, incluindo memoria agentic, eventos temporais,
series financeiras, K-lines, features quantitativas, execucoes de modelos e
previsoes Kronos.

TimescaleDB e adotada como extensao temporal oficial sobre PostgreSQL, nao como
banco separado. A versao de TimescaleDB usada pela infraestrutura deve ser
compativel com PostgreSQL 18. TimescaleDB 2.23 introduziu compatibilidade
completa com PostgreSQL 18.

Qlib sera tratado como camada de compatibilidade/projecao, nao como memoria
persistente canonica.

Kronos consumira dados financeiros por meio de uma projecao Qlib/K-line derivada
do PostgreSQL/TimescaleDB e gravara previsoes, metadados de execucao e
resultados de avaliacao de volta no mesmo PostgreSQL/TimescaleDB.

## Regras canonicas

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

## Consequencias

- Nao havera servico Qlib separado como modulo obrigatorio.
- Nao havera banco Qlib separado.
- Nao havera diretorio `~/.qlib` como fonte de verdade.
- Exportacoes `.bin`, CSV e Parquet serao caches reconstruiveis.
- Todo dataset materializado tera manifest com:
  - query hash;
  - transform version;
  - source watermark;
  - checksum;
  - created_at;
  - expires_at opcional.
- Kronos sera integrado por adapter/repository, nao por armazenamento proprio.
- A memoria temporal financeira e a memoria temporal agentic compartilham os
  mesmos principios:
  - `event_time`;
  - `ingested_at`;
  - `source_id`;
  - `schema_version`;
  - `lineage_hash`;
  - `quality_flags`.

## Escopo negativo

Este ADR nao instala TimescaleDB.

Este ADR nao altera imagem Docker.

Este ADR nao cria extension SQL.

Este ADR nao cria hypertable.

Este ADR nao cria schema financeiro.

Este ADR nao implementa Qlib, Kronos, adapters, repositories ou MCP tools.

Este ADR nao define politica de retencao, compressao ou continuous aggregates.

## Referencias

- TimescaleDB 2.23.0 release notes:
  <https://github.com/timescale/timescaledb/releases/tag/2.23.0>
- TimescaleDB changelog:
  <https://github.com/timescale/timescaledb/blob/main/CHANGELOG.md>
