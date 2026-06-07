from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


COMPOSE_PATH = Path("docker/docker-compose.postgres.yml")
LOCAL_COMPOSE_PATH = Path("infra/docker/compose.quimera.local.yml")
DOCKERFILE_PATH = Path("infra/postgres/Dockerfile")
INITDB_EXTENSIONS_PATH = Path("infra/postgres/initdb/001_extensions.sql")
WM_CHECKPOINT_SQL_PATH = Path("infra/postgres/sql/020_working_memory_checkpoints.sql")


def _compose() -> dict[str, Any]:
    raw = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def _local_compose() -> dict[str, Any]:
    raw = yaml.safe_load(LOCAL_COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def test_postgres_compose_builds_from_pinned_postgres_18_4_trixie() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])
    build = cast(dict[str, Any], postgres["build"])
    args = cast(dict[str, str], build["args"])

    assert postgres["image"] == "quimera/postgres-memory:18.4-trixie-timescaledb-pgvector"
    assert build["dockerfile"] == "infra/postgres/Dockerfile"
    assert args["POSTGRES_BASE_IMAGE"] == "postgres:18.4-trixie"
    assert args["PG_MAJOR"] == "18"
    assert args["TIMESCALEDB_VERSION"] == "2.23.0"
    assert args["PGVECTOR_VERSION"] == "0.8.2"


def test_postgres_compose_binds_loopback_only() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    assert "127.0.0.1:5432:5432" in postgres["ports"]
    assert "0.0.0.0:5432:5432" not in postgres["ports"]


def test_postgres_compose_uses_named_volume_for_memory_remount() -> None:
    compose = _compose()
    services = cast(dict[str, Any], compose["services"])
    postgres = cast(dict[str, Any], services["postgres"])
    volumes = cast(list[str], postgres["volumes"])
    environment = cast(list[str], postgres["environment"])

    assert "postgres_data:/var/lib/postgresql" in volumes
    assert "../infra/postgres/initdb:/docker-entrypoint-initdb.d:ro" in volumes
    assert "postgres_data" in compose["volumes"]
    assert (
        "../infra/postgres/secrets/postgres_password.txt:"
        "/run/secrets/quimera_postgres_password:ro"
    ) in volumes
    assert "POSTGRES_PASSWORD_FILE=/run/secrets/quimera_postgres_password" in environment
    assert "PGDATA=/var/lib/postgresql/18/docker" in environment
    assert "POSTGRES_HOST_AUTH_METHOD=trust" not in environment


def test_postgres_compose_has_healthcheck() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    healthcheck = cast(dict[str, Any], postgres["healthcheck"])
    assert "pg_isready" in " ".join(healthcheck["test"])


def test_postgres_compose_preloads_timescaledb_and_pg_stat_statements() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])
    command = cast(list[str], postgres["command"])

    assert "shared_preload_libraries=timescaledb,pg_stat_statements" in command
    assert "pg_stat_statements.track=all" in command
    assert "track_io_timing=on" in command


def test_local_quimera_compose_uses_same_postgres_extension_image() -> None:
    services = cast(dict[str, Any], _local_compose()["services"])
    postgres = cast(dict[str, Any], services["postgres-memory"])
    build = cast(dict[str, Any], postgres["build"])
    args = cast(dict[str, str], build["args"])
    command = cast(list[str], postgres["command"])

    assert postgres["image"] == "quimera/postgres-memory:18.4-trixie-timescaledb-pgvector"
    assert build["dockerfile"] == "infra/postgres/Dockerfile"
    assert args["POSTGRES_BASE_IMAGE"] == "postgres:18.4-trixie"
    assert "shared_preload_libraries=timescaledb,pg_stat_statements" in command


def test_postgres_extension_dockerfile_installs_timescaledb_and_pgvector() -> None:
    text = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "ARG POSTGRES_BASE_IMAGE=postgres:18.4-trixie" in text
    assert "ARG TIMESCALEDB_VERSION=2.23.0" in text
    assert "ARG PGVECTOR_VERSION=0.8.2" in text
    assert "github.com/timescale/timescaledb.git" in text
    assert "github.com/pgvector/pgvector.git" in text
    assert "timescaledb.control" in text
    assert "vector.control" in text


def test_initdb_bootstrap_creates_required_extensions() -> None:
    text = INITDB_EXTENSIONS_PATH.read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto;" in text
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb;" in text
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in text
    assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" in text


def test_working_memory_checkpoint_sql_creates_vector_extension() -> None:
    text = WM_CHECKPOINT_SQL_PATH.read_text(encoding="utf-8")

    assert text.startswith("CREATE EXTENSION IF NOT EXISTS vector;")
    assert "memory_vector vector(768)" in text
