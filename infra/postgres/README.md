# PostgreSQL Local Memory Container

The Quimera relational-temporal memory container uses PostgreSQL 18.4 and is
defined in `docker/docker-compose.postgres.yml`.

The runtime image is built locally as
`quimera/postgres-memory:18.4-trixie-timescaledb-pgvector` from the pinned
`postgres:18.4-trixie` base. This keeps ADR-0021's PostgreSQL version contract
while installing the native extensions required by RAG-01B:

- TimescaleDB `2.23.0` for temporal hypertables.
- pgvector `0.8.2` for durable working-memory checkpoints.

Create the local password file before starting the container:

```bash
mkdir -p infra/postgres/secrets
printf '%s\n' '<local-development-password>' > infra/postgres/secrets/postgres_password.txt
chmod 600 infra/postgres/secrets/postgres_password.txt
```

The password file is intentionally not versioned. Compose injects it with
`POSTGRES_PASSWORD_FILE`; do not commit real secrets or copy the value into
project documentation.

Start the container:

```bash
docker compose -f docker/docker-compose.postgres.yml up -d
```

PR-09 operational hardening enables `pg_stat_statements` in the local compose
command line:

- `shared_preload_libraries=timescaledb,pg_stat_statements`
- `compute_query_id=auto`
- `pg_stat_statements.max=10000`
- `pg_stat_statements.track=all`
- `track_io_timing=on`

The initdb bootstrap creates only extensions, not application tables:

- `pgcrypto`
- `timescaledb`
- `vector`
- `pg_stat_statements`

Create a local custom-format backup:

```bash
./infra/postgres/backup.sh
```

Verify a restore in a temporary database:

```bash
./infra/postgres/restore_verify.sh .runtime/backups/postgres/<dump-file>
```

Generate safe pg_stat diagnostics without query text:

```bash
python -m infra.postgres.pg_stat_report --json
```

Backups are local-only, default to `.runtime/backups/postgres`, use
`pg_dump -Fc`, and write a JSON manifest with SHA-256, size, version and restore
status. The scripts never print the full DSN.

For integration tests, build the DSN locally with the same password:

```bash
TEST_POSTGRES_DSN='postgresql://quimera:<local-development-password>@127.0.0.1:5432/quimera'
```
