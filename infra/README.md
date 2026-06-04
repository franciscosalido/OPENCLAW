# QUIMERA Local Infrastructure

This directory contains local-only infrastructure contracts for the QUIMERA
runtime.

## Local Environment

Copy the example file before starting the stack:

```bash
cp .env.local.example .env.local
```

`LITELLM_MASTER_KEY` is required. The compose file uses Docker Compose required
variable interpolation and fails fast when the value is missing instead of
starting LiteLLM with an empty key.

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

```bash
./scripts/start_quimera.sh stop --release-models
docker volume rm quimera-local_postgres_data
docker volume rm quimera-local_qdrant_data
```

The default controller does not run volume deletion or system-wide Docker prune.
