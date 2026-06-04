from __future__ import annotations

import pytest

from backend.memory.postgres.settings import PostgresSettings, sanitize_dsn


def test_settings_load_dsn_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "QUIMERA_POSTGRES_DSN",
        "postgresql://user:secret@127.0.0.1:5432/quimera_test",
    )

    settings = PostgresSettings()

    assert settings.dsn == "postgresql://user:secret@127.0.0.1:5432/quimera_test"


def test_pool_defaults_are_local_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUIMERA_POSTGRES_MIN_POOL_SIZE", raising=False)
    monkeypatch.delenv("QUIMERA_POSTGRES_MAX_POOL_SIZE", raising=False)

    settings = PostgresSettings()

    assert settings.min_pool_size >= 1
    assert settings.max_pool_size <= 10
    assert settings.min_pool_size <= settings.max_pool_size


def test_command_timeout_default_is_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUIMERA_POSTGRES_COMMAND_TIMEOUT", raising=False)

    assert PostgresSettings().command_timeout > 0


def test_settings_repr_sanitizes_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "QUIMERA_POSTGRES_DSN",
        "postgresql://user:secret@127.0.0.1:5432/quimera_test",
    )

    rendered = repr(PostgresSettings())

    assert "secret" not in rendered
    assert "***" in rendered


def test_sanitize_dsn_handles_password_and_passwordless_dsn() -> None:
    assert (
        sanitize_dsn("postgresql://user:secret@127.0.0.1:5432/db")
        == "postgresql://user:***@127.0.0.1:5432/db"
    )
    assert (
        sanitize_dsn("postgresql://user@127.0.0.1:5432/db")
        == "postgresql://user@127.0.0.1:5432/db"
    )
