# RAG-01B PR-09 - Operational Hardening + Smoke CLI

Status: Draft implementation

## Goal

PR-09 makes the RAG-01B stack more reproducible for continuous local
development and staging-style use.

It adds local PostgreSQL backup/restore verification, pg_stat_statements
diagnostics, one smoke command, a manual health report, latency baseline checks
and the working memory checkpoint contract.

## Working Memory Contract - Backend Deferred, Checkpoint Accepted

The future fast working memory backend is deferred. Redis, Python in-process
vector memory and Qdrant in-memory remain candidates only.

pgvector is accepted as the durable checkpoint for working memory. It is not
the hot layer. If the future hot memory layer crashes, QUIMERA restores working
context from pgvector checkpoint records plus canonical Postgres/Timescale
memory.

Checkpoint records must preserve agent id, session id, safe topic label,
embedding model, vector dimension, TTL, checksum, schema version and
timestamps. They must not store prompt, response, chunk, document text, DSN or
secrets.

## PostgreSQL Backup And Restore

`infra/postgres/backup.sh` creates local `pg_dump -Fc` artifacts and a JSON
manifest with hash, size, PostgreSQL version, pg_dump version and restore
status.

`infra/postgres/restore_verify.sh` restores into a temporary database prefixed
with `quimera_restore_verify_`, probes the restore and marks the manifest as
verified. It never restores into the primary database.

## pg_stat_statements

The local PostgreSQL compose config enables:

- `shared_preload_libraries=pg_stat_statements`
- `compute_query_id=auto`
- `pg_stat_statements.max=10000`
- `pg_stat_statements.track=all`
- `track_io_timing=on`

Reports omit query text by default and use safe metrics such as queryid, calls,
mean execution time, total execution time and rows.

## Smoke CLI

`./run_smoke.sh` defines the local operational gate.

Modes:

- `--quick`: start/wait/status/health only.
- `--full`: quick plus Agentic0 smoke and pg_stat report.
- `--diagnostic`: full plus detailed safe diagnostics.

The script does not use `down -v`, `docker system prune`, collection deletion
or database recreation of the primary database.

## Health Report

`python -m integration.health_report` creates JSON and Markdown reports with
service status, versions, backup status, pg_stat top queries, latency baseline
comparison and warnings.

## Out Of Scope

No final fast-memory backend is chosen. No Redis backend, Qdrant in-memory
backend, Python vector memory backend, cloud backup, PITR, replication,
dashboard, provider remoto or destructive migration is introduced.
