# PKD-D2P-00Y - Qdrant 1.18.x Server/Client Family Parity

Status: Accepted-D2P

Decision Type: D2P / Two-Way Door / Reversible

Date: 2026-06-07

## Resumo executivo

O QUIMERA adota Qdrant Server `qdrant/qdrant:v1.18.2` como alvo local atual
para a memoria vetorial.

Como o pacote Python oficial disponivel no PyPI e `qdrant-client 1.18.0`, a
paridade canonica entre servidor e cliente e por familia `1.18.x`, nao por
patch exato.

## Decisao

- Server target: `qdrant/qdrant:v1.18.2`.
- Python dependency floor: `qdrant-client>=1.18`.
- Current Python client lockfile resolution: `qdrant-client 1.18.0`.
- Required compatibility boundary: both server and client must be in the
  `1.18.x` family.
- Exact server/client patch parity is diagnostic only.
- `qdrant/qdrant:latest` remains prohibited.
- Legacy `qdrant/qdrant:v1.13.x` remains historical only.

## Evidencia operacional

Official checks performed on 2026-06-07:

- GitHub latest release: `qdrant/qdrant` reports `v1.18.2`.
- GitHub tags include `v1.18.2`, `v1.18.1` and `v1.18.0`.
- Docker Hub tags include `qdrant/qdrant:v1.18.2`.
- PyPI reports `qdrant-client 1.18.0` as the latest Python client release.

Therefore exact patch parity cannot be required without either downgrading the
server or inventing a Python client release that does not exist.

## Contrato

Readiness must record:

- `target_server_version = "1.18.2"`;
- `target_client_version = "1.18.0"` while the lockfile resolves that version;
- `version_family = "1.18"`;
- `version_family_ok = true`;
- `version_exact_parity_ok = false` when server `1.18.2` runs with client
  `1.18.0`.

Readiness fails if:

- Qdrant server is not the configured target server version;
- server or client is outside the `1.18.x` family;
- `qdrant-client` resolves below `1.18`;
- REST or gRPC health probes fail.

Readiness does not fail merely because server and client patch versions differ
inside `1.18.x`.

## Relacao com ADRs anteriores

This PKD supersedes the Qdrant version portions of:

- `docs/04_MEM/decisions.md` ADR-004, which pinned the historical
  `qdrant/qdrant:v1.13.2`;
- `docs/ADR/ADR-018-qdrant-118-upgrade.md` where it referred to
  `qdrant/qdrant:v1.18.1`.

Those documents remain useful history. Active runtime references must follow
this PKD.

## Consequencias

- Compose files must pin `qdrant/qdrant:v1.18.2`.
- `infra/qdrant/version_contract.yaml` must target server `1.18.2`.
- Tests must assert family parity and explicit target pinning, not patch parity.
- Benchmarks generated under `1.18.0` or `1.18.1` must not be relabeled as
  `1.18.2` evidence.
- New benchmark and readiness artifacts should record the actual live server
  version before execution.

## Rollback

This is reversible:

1. Change compose image and version contract back to a previous explicit tag.
2. Restart the local Qdrant container.
3. Run readiness, smoke and focused Qdrant tests.
4. Record the rollback in current state.

Allowed rollback targets are explicit tags only, for example
`qdrant/qdrant:v1.18.1` or `qdrant/qdrant:v1.18.0`.

`qdrant/qdrant:latest` is not an allowed rollback target.
