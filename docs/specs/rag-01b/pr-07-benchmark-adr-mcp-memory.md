# RAG-01B PR-07 - Benchmark, ADR and MCP Memory Gate

Status: Draft implementation

## Gate Zero - Version Drift Reconciliation

The previous PostgreSQL major-version reference was superseded by ADR-0021.

PostgreSQL 18.4 is mandatory for RAG-01B relational-temporal memory. The local
Docker tag is `postgres:18.4-trixie`, with PostgreSQL 18 compatible storage:
volume mounted at `/var/lib/postgresql` and internal `PGDATA` at
`/var/lib/postgresql/18/docker`.

The previous Qdrant minor-line reference was superseded by ADR-018.

Qdrant 1.18.x is mandatory for active vector-memory work in this sprint.

Any active compose file, test or PR-07 document that reintroduces the obsolete
PostgreSQL or Qdrant versions must fail tests. CI must not run two PostgreSQL
major versions for RAG-01B without a new accepted ADR.

## Scope

PR-07 closes RAG-01B with:

- deterministic Postgres vs Qdrant session-context benchmark artifacts;
- ADR-003 derived from the benchmark summary JSON;
- status JSON and sprint acceptance JSON commands;
- minimal OTel wiring on existing async embed/cache/Postgres paths;
- local-first FastMCP memory servers for Postgres and Qdrant;
- LiteLLM host configuration validation for local MCP servers.

## Out Of Scope

- dashboards, collectors, Grafana, Tempo, Jaeger and Prometheus;
- remote providers;
- LiteLLM Docker service;
- Qdrant collection delete/recreate;
- Kronos runtime and A2A runtime;
- production MCP auth matrix;
- Qlib export runtime.

## Benchmark Contract

The benchmark writes:

- `evaluation/results/rag_01b_session_benchmark_summary.json`
- `evaluation/results/rag_01b_session_benchmark_rows.csv`

The benchmark requires `QUIMERA_CACHE_ENABLED=0`. Real service mode is opt-in
with `QUIMERA_BENCHMARK_REAL=1`; default execution is synthetic and
deterministic.

## MCP Contract

Postgres MCP listens on `127.0.0.1:8811/mcp` using streamable HTTP. It is
read-only by default. The only write tool is `postgres_agent_state_upsert`, and
it requires `QUIMERA_MCP_POSTGRES_WRITE_ENABLED=1`.

Qdrant MCP listens on `127.0.0.1:8812/mcp` using streamable HTTP. It is
read-only and never exposes vectors by default.

LiteLLM remains a host process and registers both MCP servers with local
loopback URLs only.

## OTel Contract

PR-07 wires existing PR-06 decorators to minimal real async paths:

- embed;
- cache lookup/store/record_hit;
- Postgres turns read/write;
- Postgres agent state write.

RRF and rerank spans are emitted through benchmark probes because the core RRF
implementation is synchronous and PR-06 decorators intentionally reject sync
functions.
