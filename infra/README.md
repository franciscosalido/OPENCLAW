# QUIMERA Local Infrastructure

This directory contains local-only infrastructure contracts for the QUIMERA
runtime.

## Local Environment

Copy the example file before starting the stack:

```bash
cp .env.local.example .env.local
```

Docker Compose manages only Postgres and Qdrant. LiteLLM is a local host
Python process controlled by `scripts/start_quimera.sh` or
`infra/litellm/start_litellm.sh`.

`LITELLM_MASTER_KEY` is required by the host LiteLLM process. The Compose file
must not interpolate it because Compose does not start LiteLLM in Quimera.

The example value is a local placeholder only:

```bash
LITELLM_MASTER_KEY=quimera-dev-key-change-me
QUIMERA_LLM_API_KEY=${LITELLM_MASTER_KEY}
```

Never commit real secrets.

## Volumes

`scripts/start_quimera.sh stop` uses `docker compose down` without `-v`, so
named volumes are preserved. This is intentional for local memory durability.

Full reset of corrupted local volumes is manual and operator-owned. Stop the
stack first, then remove only the intended named volume, for example:

WARNING: `docker volume rm` permanently deletes the selected local data volume.
This is irreversible without a separate backup. Run it only after a successful
backup/restore verification or when the human operator explicitly accepts data
loss for that local dev volume.

```bash
./scripts/start_quimera.sh stop --release-models
docker volume rm quimera-local_postgres_data
docker volume rm quimera-local_qdrant_data
```

The default controller does not run volume deletion or system-wide Docker prune.
