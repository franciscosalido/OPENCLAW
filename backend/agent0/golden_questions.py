"""Golden question and citation contracts for Agent-0 evidence checks."""

from __future__ import annotations

import re
import time
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Literal, Protocol, Self, cast
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator, model_validator

from backend.ingestion.bootstrap import (
    CorpusName,
    manifest_path_for_corpus,
)
from backend.ingestion.commit_store import DUAL_CORPUS_COLLECTIONS
from backend.ingestion.manifest import CorpusDocument, load_manifest
from backend.rag.collection_guard import assert_collection_namespace


CollectionName = Literal["openclaw_internal", "openclaw_financial"]
GoldenMode = Literal["dry_run", "smoke"]
Language = Literal["pt-BR"]
RetrievalMode = Literal["fake", "qdrant"]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERNAL_QUESTIONS_PATH = REPO_ROOT / "tests" / "golden" / "internal_questions.yaml"
DEFAULT_FINANCIAL_QUESTIONS_PATH = (
    REPO_ROOT / "tests" / "golden" / "financial_questions.yaml"
)
GOLDEN_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "text",
        "query",
        "question",
        "raw_text",
        "normalized_text",
        "chunk",
        "chunks",
        "chunk_text",
        "retrieved_text",
        "vector",
        "vectors",
        "embedding",
        "embeddings",
        "payload",
        "prompt",
        "api_key",
        "authorization",
        "headers",
        "raw_exception",
        "exception_message",
        "traceback",
        "absolute_paths",
        "username",
    }
)
_QUESTION_ID_RE = re.compile(r"^[if]q-\d{3}$")


class GoldenQuestion(BaseModel):
    """One citation-only golden question contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    text: str
    expected_corpus: CorpusName
    expected_collection: CollectionName
    expected_doc_ids: tuple[str, ...]
    domain: str
    language: Language
    enabled: StrictBool

    @field_validator("question_id")
    @classmethod
    def _validate_question_id(cls, value: str) -> str:
        clean_value = value.strip()
        if not _QUESTION_ID_RE.fullmatch(clean_value):
            raise ValueError("question_id must match ^[if]q-\\d{3}$")
        return clean_value

    @field_validator("text", "domain")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("value cannot be empty")
        return clean_value

    @field_validator("expected_doc_ids")
    @classmethod
    def _validate_expected_doc_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        clean_values = tuple(doc_id.strip() for doc_id in value)
        if not clean_values or any(not doc_id for doc_id in clean_values):
            raise ValueError("expected_doc_ids must be non-empty")
        return clean_values

    @model_validator(mode="after")
    def _validate_prefix_routes_to_namespace(self) -> Self:
        if self.question_id.startswith("iq-"):
            if (
                self.expected_corpus != "internal"
                or self.expected_collection != "openclaw_internal"
            ):
                raise ValueError("iq-* questions must route to internal corpus")
        if self.question_id.startswith("fq-"):
            if (
                self.expected_corpus != "financial"
                or self.expected_collection != "openclaw_financial"
            ):
                raise ValueError("fq-* questions must route to financial corpus")
        return self


class GoldenManifest(BaseModel):
    """Manifest for one golden-question corpus namespace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: tuple[GoldenQuestion, ...]

    @model_validator(mode="after")
    def _validate_unique_question_ids(self) -> Self:
        question_ids = [question.question_id for question in self.questions]
        duplicates = {
            question_id
            for question_id in question_ids
            if question_ids.count(question_id) > 1
        }
        if duplicates:
            raise ValueError("question_id values must be unique")
        return self


@dataclass(frozen=True)
class Citation:
    """Safe retrieval evidence metadata for one cited source."""

    question_id: str
    source_id: str
    doc_id: str
    chunk_id: str
    corpus: CorpusName
    collection_name: CollectionName
    origin_path: str
    score: float
    rank: int
    retrieval_mode: RetrievalMode
    chunk_index: int | None = None

    def __post_init__(self) -> None:
        if not self.question_id.strip():
            raise ValueError("question_id cannot be empty")
        if not self.source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not self.doc_id.strip():
            raise ValueError("doc_id cannot be empty")
        if not self.chunk_id.strip():
            raise ValueError("chunk_id cannot be empty")
        if not self.origin_path.strip():
            raise ValueError("origin_path cannot be empty")
        if self.rank <= 0:
            raise ValueError("rank must be greater than zero")
        if self.score < 0:
            raise ValueError("score cannot be negative")


class GoldenRetriever(Protocol):
    """Retriever interface for citation-only golden question checks."""

    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        """Return safe citation metadata without answer or text content."""
        ...


@dataclass(frozen=True)
class GoldenHarnessResult:
    """Result object returned by the golden question harness."""

    report: dict[str, Any]


class FakeRetriever:
    """Offline retriever that returns manifest-backed citation metadata."""

    def __init__(
        self,
        documents_by_corpus: Mapping[CorpusName, Mapping[str, CorpusDocument]],
    ) -> None:
        self._documents_by_corpus = documents_by_corpus
        self.calls: list[tuple[str, str]] = []

    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        self.calls.append((question.question_id, collection))
        documents = self._documents_by_corpus[question.expected_corpus]
        citations: list[Citation] = []
        for rank, doc_id in enumerate(question.expected_doc_ids, start=1):
            document = documents[doc_id]
            citations.append(
                Citation(
                    question_id=question.question_id,
                    source_id=document.source_id,
                    doc_id=document.doc_id,
                    chunk_id=f"{document.doc_id}:0",
                    corpus=question.expected_corpus,
                    collection_name=cast(CollectionName, collection),
                    origin_path=document.origin_path,
                    score=1.0,
                    rank=rank,
                    retrieval_mode="fake",
                    chunk_index=0,
                )
            )
        return tuple(citations)


def load_golden_manifest(path: Path | str) -> GoldenManifest:
    """Load one golden question manifest with yaml.safe_load."""

    raw_manifest = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("golden manifest must be a YAML mapping")
    return GoldenManifest.model_validate(raw_manifest)


def load_all_golden_questions(
    *,
    internal_path: Path | str = DEFAULT_INTERNAL_QUESTIONS_PATH,
    financial_path: Path | str = DEFAULT_FINANCIAL_QUESTIONS_PATH,
) -> tuple[GoldenQuestion, ...]:
    """Load internal and financial golden manifests without a super-manifest."""

    manifests = (
        load_golden_manifest(internal_path),
        load_golden_manifest(financial_path),
    )
    questions = tuple(
        question for manifest in manifests for question in manifest.questions
    )
    question_ids = [question.question_id for question in questions]
    duplicates = {
        question_id for question_id in question_ids if question_ids.count(question_id) > 1
    }
    if duplicates:
        raise ValueError("question_id values must be unique across golden manifests")
    return questions


def load_corpus_documents() -> dict[CorpusName, dict[str, CorpusDocument]]:
    """Load A0-PR02 corpus manifests for cross-manifest validation."""

    documents_by_corpus: dict[CorpusName, dict[str, CorpusDocument]] = {}
    for corpus in ("internal", "financial"):
        manifest = load_manifest(manifest_path_for_corpus(corpus))
        documents_by_corpus[corpus] = {
            document.doc_id: document for document in manifest.documents
        }
    return documents_by_corpus


def validate_expected_doc_ids(
    questions: Sequence[GoldenQuestion],
    documents_by_corpus: Mapping[CorpusName, Mapping[str, CorpusDocument]],
) -> None:
    """Validate every expected doc id against its A0-PR02 corpus manifest."""

    for question in questions:
        documents = documents_by_corpus[question.expected_corpus]
        for doc_id in question.expected_doc_ids:
            if doc_id not in documents:
                raise ValueError(
                    f"question_id={question.question_id} references missing doc_id={doc_id}"
                )


def run_golden_questions(
    *,
    mode: GoldenMode = "dry_run",
    retriever: GoldenRetriever | None = None,
    internal_path: Path | str = DEFAULT_INTERNAL_QUESTIONS_PATH,
    financial_path: Path | str = DEFAULT_FINANCIAL_QUESTIONS_PATH,
) -> GoldenHarnessResult:
    """Run citation-only golden question validation."""

    if mode != "dry_run" and retriever is None:
        raise ValueError("smoke mode requires an explicit retriever")
    questions = tuple(
        question
        for question in load_all_golden_questions(
            internal_path=internal_path,
            financial_path=financial_path,
        )
        if question.enabled
    )
    documents_by_corpus = load_corpus_documents()
    validate_expected_doc_ids(questions, documents_by_corpus)
    active_retriever = retriever or FakeRetriever(documents_by_corpus)

    per_question: list[dict[str, Any]] = []
    durations: list[float] = []
    passed = 0
    for question in questions:
        started_at = time.perf_counter()
        collection = assert_collection_namespace(
            question.expected_collection,
            DUAL_CORPUS_COLLECTIONS,
        )
        citations = active_retriever.retrieve(question, collection=collection)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 3)
        durations.append(latency_ms)
        matched_doc_ids = tuple(
            citation.doc_id
            for citation in citations
            if citation.doc_id in question.expected_doc_ids
            and citation.collection_name == question.expected_collection
            and citation.corpus == question.expected_corpus
        )
        citation_present = bool(matched_doc_ids)
        if citation_present:
            passed += 1
        per_question.append(
            {
                "question_id": question.question_id,
                "expected_corpus": question.expected_corpus,
                "expected_collection": question.expected_collection,
                "expected_doc_ids": list(question.expected_doc_ids),
                "citation_present": citation_present,
                "matched_doc_ids": list(matched_doc_ids),
                "latency_ms": latency_ms,
                "status": "passed" if citation_present else "failed",
                "failure_reason": None if citation_present else "expected_citation_missing",
            }
        )

    total = len(questions)
    failed = total - passed
    report = {
        "run_id": uuid4().hex,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "total_questions": total,
        "passed": passed,
        "failed": failed,
        "coverage": _ratio(passed + failed, total),
        "citation_hit_rate": _ratio(passed, total),
        "p50_query_ms": round(median(durations), 3) if durations else 0.0,
        "p95_query_ms": round(_percentile(durations, 95), 3) if durations else 0.0,
        "per_question": per_question,
    }
    assert_golden_report_sanitized(report)
    return GoldenHarnessResult(report=report)


def write_golden_report(path: Path | str, report: Mapping[str, Any]) -> None:
    """Write a sanitized golden question report."""

    assert_golden_report_sanitized(report)
    Path(path).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assert_golden_report_sanitized(report: Mapping[str, Any]) -> None:
    """Raise if the report contains forbidden content-bearing keys."""

    forbidden_hits = _forbidden_key_hits(report)
    if forbidden_hits:
        raise ValueError(f"golden report contains forbidden keys: {forbidden_hits}")


def citation_field_names() -> frozenset[str]:
    """Return Citation field names for contract tests."""

    return frozenset(asdict(_sample_citation()).keys())


def _sample_citation() -> Citation:
    return Citation(
        question_id="iq-001",
        source_id="source",
        doc_id="doc",
        chunk_id="doc:0",
        corpus="internal",
        collection_name="openclaw_internal",
        origin_path="docs/source.md",
        score=1.0,
        rank=1,
        retrieval_mode="fake",
    )


def _forbidden_key_hits(value: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text in GOLDEN_FORBIDDEN_KEYS:
                hits.append(next_path)
            hits.extend(_forbidden_key_hits(nested, next_path))
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            hits.extend(_forbidden_key_hits(nested, f"{path}[{index}]"))
    return hits


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]
