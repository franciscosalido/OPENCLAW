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

`mutmut` is configured in `pyproject.toml` to mutate `backend/` only through
the current `source_paths` key, copy the required project context, and avoid
symlink-based `mutants/` directories.

Mutation score is a quality signal, not a substitute for service-aware testing.
For QUIMERA, isolated mutation runs underestimate the stack because many tests
depend on Postgres, Qdrant, LiteLLM or Ollama. The preferred Deep run is:

```bash
scripts/vibe_deep_run.sh 'mutmut run'
```

Keep `mutate_only_covered_lines = false`. This is intentional: the Deep report
must continue showing code paths with no executable tests instead of reporting
a prettier score over covered lines only.

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

## Qdrant Client Compatibility Warning

Status: temporary compatibility filter.

The Vibe sandbox currently locks `qdrant-client 1.18.0` while the local server
target is `qdrant/qdrant:v1.18.2`. This is compatible under the QUIMERA Qdrant
policy because client/server parity is accepted by `1.18.x` family and the
client compatibility check compares the major/minor series.

`qdrant-client >=1.17.1` moved server-version probing to a daemon thread. In a
Docker test container, a client initialized with `localhost:6333` can probe the
container loopback instead of the host or QUIMERA network service. That
background probe fails and emits `UserWarning: Failed to obtain server version`
even when the locked client and live server are compatible.

The project suppresses only that known warning in two layers:

- `pyproject.toml` under `tool.pytest.ini_options.filterwarnings`, for normal
  pytest-controlled warning flow.
- `tests/conftest.py` via `warnings.filterwarnings`, for daemon-thread warnings
  emitted outside ordinary pytest capture.

This is not a blanket Qdrant warning suppression. It targets only the server
version probe warning. Real Qdrant test failures should still fail tests.

Removal rule:

1. When PyPI publishes `qdrant-client >=1.18.2`, run:

   ```bash
   uv lock --upgrade-package qdrant-client
   ```

2. Remove the Qdrant warning filters from `pyproject.toml` and
   `tests/conftest.py`.
3. Re-run Vibe smoke/deep tests with warnings enabled, including `-W always`.
