"""Deterministic fingerprints for controlled corpus ingestion."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path


_WHITESPACE_RE = re.compile(r"\s+")


def file_sha256(path: Path) -> str:
    """Return sha256 over the raw file bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as raw_file:
        for block in iter(lambda: raw_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bytes_sha256(raw_bytes: bytes) -> str:
    """Return sha256 over raw bytes."""

    return hashlib.sha256(raw_bytes).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize parsed text for stable content fingerprints."""

    return _WHITESPACE_RE.sub(" ", text).strip()


def normalized_text_sha256(text: str) -> str:
    """Return sha256 over normalized parsed text."""

    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def duplicate_hashes(file_hashes_by_doc_id: Mapping[str, str]) -> set[str]:
    """Return doc_ids whose file hash duplicates an earlier document."""

    seen_hashes: set[str] = set()
    duplicate_doc_ids: set[str] = set()
    for doc_id, digest in file_hashes_by_doc_id.items():
        if digest in seen_hashes:
            duplicate_doc_ids.add(doc_id)
        else:
            seen_hashes.add(digest)
    return duplicate_doc_ids


def unique_hash_count(file_hashes: Iterable[str]) -> int:
    """Return the number of unique raw-file hashes."""

    return len(set(file_hashes))
