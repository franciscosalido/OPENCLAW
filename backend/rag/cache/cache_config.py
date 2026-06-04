"""Settings for the HybridRAG semantic retrieval cache."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CacheDistance = Literal["Cosine", "Dot", "Euclid", "Manhattan"]


class CacheSettings(BaseSettings):
    """Environment-backed cache settings."""

    model_config = SettingsConfigDict(
        env_prefix="QUIMERA_CACHE_",
        env_ignore_empty=True,
        extra="ignore",
    )

    enabled: bool = True
    collection_name: str = "quimera_query_cache"
    threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    vector_size: int = Field(default=1024, gt=0)
    distance: CacheDistance = "Cosine"
    embedding_model: str = "qwen3-embedding"
    profile_name: str = "default"
    source_collection: str = "quimera_knowledge"
    corpus_epoch: str = "dev"
    default_ttl_seconds: int | None = Field(default=None, gt=0)
    max_result_docs: int = Field(default=50, gt=0)
    hot_entries_oversample_factor: int = Field(default=3, ge=1)

    @field_validator(
        "collection_name",
        "embedding_model",
        "profile_name",
        "source_collection",
        "corpus_epoch",
        mode="after",
    )
    @classmethod
    def required_text_must_not_be_empty(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("cache setting cannot be empty")
        return clean

    @model_validator(mode="after")
    def validate_collection_boundaries(self) -> Self:
        """Keep the cache collection separate from the source collection."""

        if self.collection_name == self.source_collection:
            raise ValueError("collection_name and source_collection must differ")
        return self

    @property
    def similarity_threshold(self) -> float:
        """Return the configured lookup score threshold."""

        return self.threshold


@lru_cache(maxsize=1)
def get_cache_settings() -> CacheSettings:
    """Return cached settings; tests may call cache_clear on this function."""

    return CacheSettings()
