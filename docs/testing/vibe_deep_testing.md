# Vibe Deep Testing

Status: active operational contract.

## Official Sandbox

The official Vibe sandbox image is `vibe-sandbox:py312` and must be built from
`Dockerfile.openclaw-sandbox`.

The Dockerfile is pinned to Python 3.12 because OpenClaw requires Python 3.12
semantics across `pyproject.toml`, mypy, pyright and CI. Do not publish a
`py312` image from a Python 3.13 or 3.14 base.

The image owns `/opt/openclaw-venv`. The repository is mounted at `/workspace`
at runtime and then installed editable with:

```bash
scripts/vibe_sandbox_bootstrap.sh /workspace
```

This keeps dependencies inside the image while still testing the current host
checkout.

## Dynamic Stack Access

Use the dynamic runner when mutation, integration, smoke or e2e tests need the
live QUIMERA stack:

```bash
scripts/vibe_deep_run.sh
```

The runner rebuilds the image with `docker build --pull`, mounts the current
checkout at `/workspace`, enables `QUIMERA_E2E=true`, and attaches the
container to the first available QUIMERA network:

1. `QUIMERA_VIBE_DOCKER_NETWORK`, when explicitly set.
2. `quimera_network`, when present.
3. `quimera-local_default`, the default network from
   `infra/docker/compose.quimera.local.yml`.

When attached to the QUIMERA network, Postgres and Qdrant are reached by
container DNS names. Host services such as LiteLLM and Ollama remain reachable
through `host.docker.internal`.

## Mutation Testing

`mutmut` is configured in `pyproject.toml` to mutate `backend/` only, copy the
required project context, and avoid symlink-based `mutants/` directories.

Mutation score is a quality signal, not a substitute for service-aware testing.
For QUIMERA, isolated mutation runs underestimate the stack because many tests
depend on Postgres, Qdrant, LiteLLM or Ollama. The preferred Deep run is:

```bash
scripts/vibe_deep_run.sh 'mutmut run'
```

The runner must not print DSNs or secrets. If the local Postgres password file
exists, it is read inside the container only to build `TEST_POSTGRES_DSN`.

## Virtualenv Patio

Keep:

- `/Users/fas/projetos/OPENCLAW/.venv`
- `/opt/openclaw-venv` inside the sandbox image

Do not delete virtualenvs directly. Move disposable or suspicious virtualenvs to
the patio first:

```bash
scripts/quarantine_venv_to_patio.sh /Users/fas/projetos/vibe_code_sandbox/.venv
```

The default patio is:

```text
/Users/fas/projetos/_patio_venvs
```

Keep `infra/litellm/.venv` on disk until the LiteLLM host smoke has passed
without it. Runtime startup now prefers the project root `.venv` and then
`uv run litellm`; the old infra-local venv is no longer part of the normal
startup path.

## Dependency Security Notes

`uv.lock` is the source of truth for the sandbox build. If pip-audit or Trivy
reports a version older than the lock, rebuild `vibe-sandbox:py312` before
treating the finding as current.

Current Deep hardening expectations:

- PyJWT must be `>=2.13.0`.
- urllib3 must be `>=2.7.0`.
- Semgrep runs outside the project venv.
- Reports and `mutants/` are generated artifacts and must remain untracked.
