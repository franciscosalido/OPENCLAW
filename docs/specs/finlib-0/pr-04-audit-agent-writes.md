# FL-PR04 — Audit Agent Writes

Status: Implementation branch

Branch: `feat/finlib-audit-agent-writes`

## Objetivo

Criar uma tabela append-only para auditoria de escritas futuras dos data
agents e repositories FINLIB. Este PR é pré-agente e pré-repository: ele cria
somente o contrato de armazenamento auditável.

## Schema Diff

### `audit_agent_writes`

- `audit_id UUID PRIMARY KEY DEFAULT uuidv7()`
- `trace_id UUID NOT NULL`
- `run_id UUID REFERENCES ops_ingestion_runs(run_id)`
- `agent_id TEXT NOT NULL`
- `repository TEXT NOT NULL`
- `target_table TEXT NOT NULL`
- `operation TEXT NOT NULL`
- `row_count INTEGER NOT NULL`
- `batch_hash TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

`agent_id`, `repository`, `target_table` and `batch_hash` must contain at
least one non-whitespace character. `metadata` must be a JSON object.

Allowed operations are exactly `insert`, `update`, `upsert`, `bulk_insert` and
`bulk_upsert`. `delete` is intentionally absent from the audit operation
domain for FL-PR04.

`row_count >= 0` is allowed so idempotent logical batches can be audited even
when they produce no material row changes. `batch_hash` is a lineage/hash value
for the logical batch, never a raw payload.

## Append-Only Enforcement

`audit_agent_writes` is append-only by database trigger:

- `INSERT` is allowed.
- `UPDATE` is rejected.
- `DELETE` is rejected.
- Corrections must be recorded as new rows.

The migration also revokes `UPDATE` and `DELETE` from `PUBLIC` as
defense-in-depth. In the current single-role local setup, PostgreSQL object
owners still retain owner capabilities; therefore the trigger is the
authoritative enforcement layer. Future split-role deployments should grant
application roles only the minimum required `INSERT`/`SELECT` privileges.

## Future Repository Transaction Contract

Every future repository write must commit the domain write and the audit write
in the same transaction:

```sql
BEGIN;
  -- write logical batch into target domain table
  -- insert exactly one audit_agent_writes row for that logical batch
COMMIT;
```

If the audit insert fails, the domain write must roll back. If the domain write
fails, no orphan audit row should be created. Each logical batch must produce
exactly one audit row.

Each logical batch must produce exactly one audit row.

## Fora de Escopo

- repositories
- data agents
- MCP write tools
- runtime A2A
- FL-PR05+ financial library tables
- Qdrant, pgvector or LiteLLM changes
