"""Manifest contract for controlled Agent-0 corpus ingestion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal["md", "pdf"]
CurationStatus = Literal["approved", "pending", "rejected"]
IngestionPolicy = Literal["internal", "financial"]
Language = Literal["pt-BR"]

MANIFEST_DOCUMENTS_KEY = "documents"
_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,127}$")


class CorpusDocument(BaseModel):
    """One curated corpus document declared by the manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    doc_id: str
    origin_path: str
    source_type: SourceType
    domain: str
    language: Language
    license: str
    contains_pii: bool
    curation_status: CurationStatus
    ingestion_policy: IngestionPolicy
    enabled: bool
    expected_hash: str | None = None
    expected_normalized_text_hash: str | None = None
    notes: str | None = None

    @field_validator("source_id")
    @classmethod
    def _validate_source_id(cls, value: str) -> str:
        clean_value = value.strip()
        if not _STABLE_ID_RE.fullmatch(clean_value):
            raise ValueError("source_id must be a stable non-empty slug or UUID-like string")
        return clean_value

    @field_validator("doc_id", "domain", "license")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("value cannot be empty")
        return clean_value

    @field_validator("expected_hash", "expected_normalized_text_hash")
    @classmethod
    def _validate_optional_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean_value = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", clean_value):
            raise ValueError("expected hashes must be lowercase sha256 hex strings")
        return clean_value

    @field_validator("origin_path")
    @classmethod
    def _validate_origin_path(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("origin_path cannot be empty")

        path = Path(clean_value)
        if path.is_absolute():
            raise ValueError("origin_path must be relative to data/corpus")
        if any(part in {"..", ""} for part in path.parts):
            raise ValueError("origin_path cannot contain path traversal")
        return path.as_posix()

    @model_validator(mode="after")
    def _validate_suffix_matches_type(self) -> Self:
        suffix = Path(self.origin_path).suffix.lower().lstrip(".")
        if suffix != self.source_type:
            raise ValueError("origin_path suffix must match source_type")
        return self


class CorpusManifest(BaseModel):
    """Contract-first manifest for a curated corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=1)
    documents: tuple[CorpusDocument, ...]

    @model_validator(mode="after")
    def _validate_unique_document_ids(self) -> Self:
        doc_ids = [document.doc_id for document in self.documents]
        duplicates = {doc_id for doc_id in doc_ids if doc_ids.count(doc_id) > 1}
        if duplicates:
            raise ValueError("doc_id values must be unique")
        source_ids = [document.source_id for document in self.documents]
        dup_source_ids = {
            source_id for source_id in source_ids if source_ids.count(source_id) > 1
        }
        if dup_source_ids:
            raise ValueError("source_id values must be unique")
        return self


def load_manifest(path: Path) -> CorpusManifest:
    """Load a corpus manifest using yaml.safe_load only."""

    with path.open("r", encoding="utf-8") as manifest_file:
        raw_manifest = yaml.safe_load(manifest_file)

    if not isinstance(raw_manifest, Mapping):
        raise ValueError("manifest must be a YAML mapping")
    if MANIFEST_DOCUMENTS_KEY not in raw_manifest:
        raise ValueError("manifest must contain documents")
    return CorpusManifest.model_validate(raw_manifest)


def resolve_corpus_path(manifest_path: Path, document: CorpusDocument) -> Path:
    """Resolve one manifest path under the manifest's corpus directory."""

    corpus_root = manifest_path.resolve().parent
    candidate = (corpus_root / document.origin_path).resolve()
    if not candidate.is_relative_to(corpus_root):
        raise ValueError("origin_path escaped data/corpus")
    return candidate
