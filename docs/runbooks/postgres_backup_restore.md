# PostgreSQL Backup And Restore Runbook

Generate a local backup:

```bash
./infra/postgres/backup.sh
```

Verify restore in an isolated temporary database:

```bash
./infra/postgres/restore_verify.sh .runtime/backups/postgres/<dump-file>
```

List backups:

```bash
ls .runtime/backups/postgres
```

Interpret the manifest:

- `sha256` proves dump integrity.
- `dump_size_bytes` records artifact size.
- `postgres_version` and `pg_dump_version` record tooling.
- `restore_verified=true` means restore verification completed.

Safety:

- never restore into the primary database without manual human confirmation.
- never use down -v.
- nunca usar down -v.
- never print DSN.
- never commit dump files or manifests with private data.
