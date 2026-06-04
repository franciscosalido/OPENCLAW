from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


COMPOSE_PATH = Path("docker/docker-compose.postgres.yml")


def _compose() -> dict[str, Any]:
    raw = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def test_postgres_compose_exists_and_pins_postgres_16() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    assert postgres["image"] == "postgres:16"


def test_postgres_compose_binds_loopback_only() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    assert "127.0.0.1:5432:5432" in postgres["ports"]
    assert "0.0.0.0:5432:5432" not in postgres["ports"]


def test_postgres_compose_uses_named_volume_for_memory_remount() -> None:
    compose = _compose()
    services = cast(dict[str, Any], compose["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    assert "postgres_data:/var/lib/postgresql/data" in postgres["volumes"]
    assert "postgres_data" in compose["volumes"]


def test_postgres_compose_has_healthcheck() -> None:
    services = cast(dict[str, Any], _compose()["services"])
    postgres = cast(dict[str, Any], services["postgres"])

    healthcheck = cast(dict[str, Any], postgres["healthcheck"])
    assert "pg_isready" in " ".join(healthcheck["test"])
