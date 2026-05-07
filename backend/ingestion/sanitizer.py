"""PII guardrails for controlled corpus ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.ingestion.manifest import CorpusDocument


SanitizerStatus = Literal["accepted", "contains_pii_manifest", "pii_detected"]
PiiPatternCategory = Literal[
    "cpf_punctuated",
    "cpf_unformatted",
    "email",
    "br_phone",
]

_PII_PATTERNS: tuple[tuple[PiiPatternCategory, re.Pattern[str]], ...] = (
    ("cpf_punctuated", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")),
    ("cpf_unformatted", re.compile(r"(?<!\d)\d{11}(?!\d)")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "br_phone",
        re.compile(r"(?<!\d)(?:\+55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\s*)?\d{4}[-\s]?\d{4}(?!\d)"),
    ),
)


@dataclass(frozen=True)
class SanitizerResult:
    """Safe sanitizer result that never includes matched sensitive text."""

    status: SanitizerStatus
    pii_pattern_category: PiiPatternCategory | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


def reject_manifest_pii(document: CorpusDocument) -> SanitizerResult:
    """Reject manifest-declared PII before parsing heavy content."""

    if document.contains_pii:
        return SanitizerResult(status="contains_pii_manifest")
    return SanitizerResult(status="accepted")


def sanitize_parsed_text(text: str) -> SanitizerResult:
    """Detect supported PII categories without returning matched values."""

    for category, pattern in _PII_PATTERNS:
        if pattern.search(text):
            return SanitizerResult(status="pii_detected", pii_pattern_category=category)
    return SanitizerResult(status="accepted")
