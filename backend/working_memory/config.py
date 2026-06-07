"""Settings for QUIMERA hot working memory."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


WorkingMemoryDistance = Literal["Cosine", "Dot", "Euclid", "Manhattan"]


class WorkingMemorySettings(BaseSettings):
    """Environment-backed settings for Qdrant working memory."""

    model_config = SettingsConfigDict(
        env_prefix="QUIMERA_WM_",
        env_ignore_empty=True,
        extra="ignore",
    )

    enabled: bool = True
    qdrant_url: str = "http://127.0.0.1:6333"
    collection_name: str = Field(
        default="quimera_working_memory",
        validation_alias=AliasChoices("QUIMERA_WM_COLLECTION", "collection_name"),
    )
    vector_name: str = "work-dense"
    vector_size: int = Field(default=768, gt=0)
    distance: WorkingMemoryDistance = "Cosine"
    default_ttl_seconds: int = Field(default=3600, gt=0)
    max_points_per_session: int = Field(default=512, gt=0)
    snapshot_every_writes: int = Field(default=20, gt=0)
    snapshot_interval_seconds: int = Field(default=300, gt=0)
    restore_enabled: bool = False
    cleanup_enabled: bool = False

    @field_validator("qdrant_url", mode="after")
    @classmethod
    def validate_local_qdrant_url(cls, value: str) -> str:
        clean = value.strip()
        parsed = urlparse(clean)
        if parsed.scheme != "http":
            raise ValueError("working memory qdrant_url must use local http")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("working memory qdrant_url must be loopback-local")
        return clean

    @field_validator("collection_name", mode="after")
    @classmethod
    def validate_collection_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean.startswith("quimera_working_memory"):
            raise ValueError(
                "working memory collection must use quimera_working_memory prefix"
            )
        if clean in {"quimera_knowledge", "quimera_query_cache", "quimera_llm_cache"}:
            raise ValueError(
                "working memory collection must not reuse knowledge/cache collections"
            )
        return clean

    @field_validator("vector_name", mode="after")
    @classmethod
    def validate_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("working memory text setting cannot be empty")
        return clean

    @model_validator(mode="after")
    def validate_runtime_bounds(self) -> Self:
        if self.collection_name in {
            "quimera_knowledge",
            "quimera_query_cache",
            "quimera_llm_cache",
        }:
            raise ValueError("working memory collection must be isolated")
        return self


@lru_cache(maxsize=1)
def get_working_memory_settings() -> WorkingMemorySettings:
    """Return cached working-memory settings."""

    return WorkingMemorySettings()
