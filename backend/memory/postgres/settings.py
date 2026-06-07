"""PostgreSQL memory settings loaded from environment."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_POSTGRES_DSN = "postgresql://quimera@127.0.0.1:5432/quimera"


class PostgresSettings(BaseSettings):
    """Local-first settings for the asyncpg memory pool."""

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    dsn: str = Field(
        default=DEFAULT_POSTGRES_DSN, validation_alias="QUIMERA_POSTGRES_DSN"
    )
    min_pool_size: int = Field(
        default=1, validation_alias="QUIMERA_POSTGRES_MIN_POOL_SIZE"
    )
    max_pool_size: int = Field(
        default=5, validation_alias="QUIMERA_POSTGRES_MAX_POOL_SIZE"
    )
    command_timeout: float = Field(
        default=30.0,
        validation_alias="QUIMERA_POSTGRES_COMMAND_TIMEOUT",
    )

    @model_validator(mode="after")
    def _validate_pool_bounds(self) -> "PostgresSettings":
        if self.min_pool_size < 1:
            raise ValueError("min_pool_size must be >= 1")
        if self.max_pool_size < self.min_pool_size:
            raise ValueError("max_pool_size must be >= min_pool_size")
        if self.max_pool_size > 10:
            raise ValueError("max_pool_size must be <= 10 for local-first defaults")
        if self.command_timeout <= 0:
            raise ValueError("command_timeout must be > 0")
        return self

    def __repr__(self) -> str:
        return (
            "PostgresSettings("
            f"dsn={sanitize_dsn(self.dsn)!r}, "
            f"min_pool_size={self.min_pool_size!r}, "
            f"max_pool_size={self.max_pool_size!r}, "
            f"command_timeout={self.command_timeout!r})"
        )


def sanitize_dsn(dsn: str) -> str:
    """Return a DSN with password redacted, preserving passwordless URLs."""

    parts = urlsplit(dsn)
    if not parts.password:
        return dsn
    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
