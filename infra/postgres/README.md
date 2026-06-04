# PostgreSQL Local Memory Container

The Quimera relational-temporal memory container uses PostgreSQL 18.4 and is
defined in `docker/docker-compose.postgres.yml`.

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

For integration tests, build the DSN locally with the same password:

```bash
TEST_POSTGRES_DSN='postgresql://quimera:<local-development-password>@127.0.0.1:5432/quimera'
```
