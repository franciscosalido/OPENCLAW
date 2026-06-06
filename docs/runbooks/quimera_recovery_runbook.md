# Quimera Recovery Runbook

1. Verify health:

```bash
./scripts/start_quimera.sh status --json
```

2. Run the quick operational gate:

```bash
./run_smoke.sh --quick
```

3. Generate a backup:

```bash
./infra/postgres/backup.sh
```

4. Test restore:

```bash
./infra/postgres/restore_verify.sh .runtime/backups/postgres/<dump-file>
```

5. Interpret pg_stat_report:

```bash
python -m infra.postgres.pg_stat_report --json
```

6. Restart services without deleting volumes:

```bash
./scripts/start_quimera.sh restart
```

7. Confirm Agentic0:

```bash
./scripts/start_quimera.sh agentic0-smoke --json
```

8. Confirm working memory checkpoint contract:

```bash
rg working_memory_checkpoints infra/postgres/sql
```

9. Escalate to a future PR for PITR, offsite backup, dashboards, full
multi-agent permissions or final working memory backend selection.
