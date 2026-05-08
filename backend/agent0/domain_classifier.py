"""Deterministic Agent-0 domain classifier.

This module intentionally uses only local string and regex rules. It must not
import model clients, embedders, retrievers or vector stores.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


DomainName = Literal["internal", "macroeconomia", "renda_fixa", "valuation", "unknown"]
CorpusName = Literal["internal", "financial", "none"]
CollectionName = Literal["openclaw_internal", "openclaw_financial", "none"]


@dataclass(frozen=True)
class DomainClassification:
    """Safe metadata returned by the deterministic classifier."""

    domain: DomainName
    corpus: CorpusName
    collection_name: CollectionName
    reason_code: str
    matched_rule: str | None = None

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty")
        if self.matched_rule is not None and not self.matched_rule.strip():
            raise ValueError("matched_rule cannot be empty")


_DOMAIN_COLLECTIONS: dict[DomainName, tuple[CorpusName, CollectionName]] = {
    "internal": ("internal", "openclaw_internal"),
    "macroeconomia": ("financial", "openclaw_financial"),
    "renda_fixa": ("financial", "openclaw_financial"),
    "valuation": ("financial", "openclaw_financial"),
    "unknown": ("none", "none"),
}

_KEYWORD_RULES: tuple[tuple[DomainName, str, tuple[str, ...]], ...] = (
    (
        "internal",
        "keyword_internal",
        (
            "gw-07",
            "gw07",
            "gateway",
            "alias",
            "aliases",
            "claude",
            "current_state",
            "decisions",
            "timeout",
        ),
    ),
    (
        "macroeconomia",
        "keyword_selic",
        (
            "selic",
            "inflacao",
            "cambio",
            "juros",
            "ipca",
            "macroeconomia",
        ),
    ),
    (
        "renda_fixa",
        "keyword_duration",
        (
            "duration",
            "renda fixa",
            "prefixado",
            "pos-fixado",
            "credito privado",
            "curva de juros",
        ),
    ),
    (
        "valuation",
        "keyword_ebitda",
        (
            "valuation",
            "ebitda",
            "fluxo de caixa",
            "multiplo",
            "margem de seguranca",
        ),
    ),
)

_REGEX_RULES: tuple[tuple[DomainName, str, re.Pattern[str]], ...] = (
    ("internal", "regex_gateway_id", re.compile(r"\bgw-?\d+\b")),
    ("macroeconomia", "regex_macro_index", re.compile(r"\b(ipca|selic)\b")),
    ("renda_fixa", "regex_duration", re.compile(r"\bduration\b")),
    ("valuation", "regex_ebitda", re.compile(r"\bebitda\b")),
)


def classify_domain(query: str, question_id: str | None = None) -> DomainClassification:
    """Classify a query into an Agent-0 corpus domain with no model calls."""

    clean_query = _normalize_query(query)
    clean_question_id = question_id.strip().lower() if question_id else None

    if clean_question_id:
        prefix_classification = _classify_by_question_prefix(clean_question_id)
        if prefix_classification is not None:
            domain_hint = _classify_by_rules(clean_query)
            if domain_hint.domain != "unknown":
                return domain_hint
            return prefix_classification

    return _classify_by_rules(clean_query)


def _classify_by_question_prefix(question_id: str) -> DomainClassification | None:
    if question_id.startswith("iq-"):
        return _classification(
            "internal",
            reason_code="question_id_internal",
            matched_rule="iq-*",
        )
    if question_id.startswith("fq-"):
        return DomainClassification(
            domain="unknown",
            corpus="financial",
            collection_name="openclaw_financial",
            reason_code="question_id_financial",
            matched_rule="fq-*",
        )
    return None


def _classify_by_rules(clean_query: str) -> DomainClassification:
    for domain, reason_code, keywords in _KEYWORD_RULES:
        for keyword in keywords:
            if keyword in clean_query:
                return _classification(
                    domain,
                    reason_code=reason_code,
                    matched_rule=keyword,
                )

    for domain, reason_code, pattern in _REGEX_RULES:
        match = pattern.search(clean_query)
        if match is not None:
            return _classification(
                domain,
                reason_code=reason_code,
                matched_rule=pattern.pattern,
            )

    return _classification("unknown", reason_code="no_domain_match")


def _classification(
    domain: DomainName,
    *,
    reason_code: str,
    matched_rule: str | None = None,
) -> DomainClassification:
    corpus, collection_name = _DOMAIN_COLLECTIONS[domain]
    return DomainClassification(
        domain=domain,
        corpus=corpus,
        collection_name=collection_name,
        reason_code=reason_code,
        matched_rule=matched_rule,
    )


def _normalize_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query cannot be empty")
    normalized = unicodedata.normalize("NFKD", clean_query.lower())
    return "".join(character for character in normalized if not unicodedata.combining(character))
