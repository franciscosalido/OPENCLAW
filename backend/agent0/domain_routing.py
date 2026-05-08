"""Deterministic Agent-0 domain routing policy."""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Literal, Protocol, cast

import yaml

from backend.agent0.domain_classifier import (
    CollectionName,
    CorpusName,
    DomainClassification,
    DomainName,
    classify_domain,
)
from backend.agent0.golden_questions import load_all_golden_questions
from backend.ingestion.commit_store import DUAL_CORPUS_COLLECTIONS
from backend.rag.collection_guard import assert_collection_namespace


RouteName = Literal["local_rag", "local_think", "local_chat"]
RoutingMode = Literal["deterministic"]
DEFAULT_RAG_CONFIG_PATH = Path("config/rag_config.yaml")
ALLOWED_DOMAIN_NAMES = frozenset(
    {"internal", "macroeconomia", "renda_fixa", "valuation", "unknown"}
)
ALLOWED_CORPORA = frozenset({"internal", "financial", "none"})
ALLOWED_COLLECTIONS = frozenset({"openclaw_internal", "openclaw_financial", "none"})


@dataclass(frozen=True)
class DomainRuleConfig:
    """Config-backed domain rule metadata."""

    domain: DomainName
    corpus: CorpusName
    collection_name: CollectionName
    keywords: tuple[str, ...]
    regex: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.domain not in ALLOWED_DOMAIN_NAMES:
            raise ValueError("domain is not allowed")
        if self.corpus not in ALLOWED_CORPORA:
            raise ValueError("corpus is not allowed")
        if self.collection_name not in ALLOWED_COLLECTIONS:
            raise ValueError("collection_name is not allowed")
        for keyword in self.keywords:
            _validate_non_empty(keyword, "keyword")
        for pattern in self.regex:
            _validate_non_empty(pattern, "regex")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("regex pattern must compile") from exc


@dataclass(frozen=True)
class DomainRoutingConfig:
    """Agent-0 routing thresholds loaded from ``config/rag_config.yaml``."""

    retrieval_score_min: float
    escalate_to_think_below: float
    p95_routing_budget_ms: float
    citation_weight: float
    domain_rules: Mapping[DomainName, DomainRuleConfig]

    def __post_init__(self) -> None:
        if not 0 < self.escalate_to_think_below < self.retrieval_score_min <= 1.0:
            raise ValueError(
                "domain routing thresholds must satisfy "
                "0 < escalate_to_think_below < retrieval_score_min <= 1.0"
            )
        if self.p95_routing_budget_ms <= 0:
            raise ValueError("p95_routing_budget_ms must be greater than zero")
        if not 0 <= self.citation_weight <= 1.0:
            raise ValueError("citation_weight must be between zero and one")
        for domain, rule in self.domain_rules.items():
            if domain != rule.domain:
                raise ValueError("domain_rules keys must match rule domain")


@dataclass(frozen=True)
class RetrievalConfidence:
    """Safe retrieval confidence signals supplied by a scorer."""

    score: float
    top_score: float
    citation_present: bool
    citation_count: int

    def __post_init__(self) -> None:
        _validate_score(self.score, "score")
        _validate_score(self.top_score, "top_score")
        if self.citation_count < 0:
            raise ValueError("citation_count cannot be negative")


class ConfidenceScorer(Protocol):
    """Protocol for deterministic retrieval confidence scoring."""

    def score(
        self,
        *,
        query: str,
        classification: DomainClassification,
        state: "SystemState",
        config: DomainRoutingConfig,
    ) -> RetrievalConfidence:
        """Return retrieval confidence without mutating stores or calling LLMs."""
        ...


@dataclass(frozen=True)
class FakeConfidenceScorer:
    """Offline confidence scorer for unit tests and dry-run benchmarks."""

    default_score: float
    scores_by_domain: Mapping[DomainName, float] | None = None
    citation_present: bool = True
    citation_count: int = 1

    def __post_init__(self) -> None:
        _validate_score(self.default_score, "default_score")
        if self.scores_by_domain is not None:
            for domain, score in self.scores_by_domain.items():
                if domain not in ALLOWED_DOMAIN_NAMES:
                    raise ValueError("scores_by_domain contains invalid domain")
                _validate_score(score, "domain score")
        if self.citation_count < 0:
            raise ValueError("citation_count cannot be negative")

    def score(
        self,
        *,
        query: str,
        classification: DomainClassification,
        state: "SystemState",
        config: DomainRoutingConfig,
    ) -> RetrievalConfidence:
        del query, state, config
        score = self.default_score
        if self.scores_by_domain is not None:
            score = self.scores_by_domain.get(classification.domain, self.default_score)
        return RetrievalConfidence(
            score=score,
            top_score=score,
            citation_present=self.citation_present,
            citation_count=self.citation_count,
        )


@dataclass(frozen=True)
class SystemState:
    """Minimal local system state needed by the deterministic router."""

    qdrant_available: bool


@dataclass(frozen=True)
class RouteDecision:
    """Safe allowlisted Agent-0 routing decision."""

    route: RouteName
    corpus: CorpusName
    domain: DomainName
    collection_name: CollectionName
    confidence_score: float
    threshold_used: str
    reason_code: str
    latency_ms: float
    fallback_reason: str | None
    routing_mode: RoutingMode

    def __post_init__(self) -> None:
        _validate_score(self.confidence_score, "confidence_score")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        _validate_non_empty(self.threshold_used, "threshold_used")
        _validate_non_empty(self.reason_code, "reason_code")
        if self.fallback_reason is not None:
            _validate_non_empty(self.fallback_reason, "fallback_reason")

    def to_dict(self) -> dict[str, object]:
        """Return safe allowlisted metadata only."""

        data: dict[str, object] = {
            "route": self.route,
            "corpus": self.corpus,
            "domain": self.domain,
            "collection_name": self.collection_name,
            "confidence_score": round(self.confidence_score, 6),
            "threshold_used": self.threshold_used,
            "reason_code": self.reason_code,
            "latency_ms": round(self.latency_ms, 3),
            "routing_mode": self.routing_mode,
        }
        if self.fallback_reason is not None:
            data["fallback_reason"] = self.fallback_reason
        return data


@dataclass(frozen=True)
class GoldenRoutingGateResult:
    """Aggregate result for routing A0-PR03 golden questions."""

    total_questions: int
    passed: int
    failed: int
    accuracy: float
    p95_routing_ms: float
    decisions: tuple[RouteDecision, ...]


def load_domain_routing_config(
    config_path: Path | str = DEFAULT_RAG_CONFIG_PATH,
) -> DomainRoutingConfig:
    """Load Agent-0 domain routing thresholds from ``rag_config.yaml``."""

    raw_config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw_config, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    agent0 = raw_config.get("agent0")
    if not isinstance(agent0, Mapping):
        raise ValueError("rag_config.yaml must contain agent0 mapping")
    routing = agent0.get("domain_routing")
    if not isinstance(routing, Mapping):
        raise ValueError("rag_config.yaml must contain agent0.domain_routing mapping")

    raw_rules = routing.get("domain_rules")
    if not isinstance(raw_rules, Mapping):
        raise ValueError("agent0.domain_routing.domain_rules must be a mapping")
    domain_rules: dict[DomainName, DomainRuleConfig] = {}
    for domain_text, raw_rule in raw_rules.items():
        if not isinstance(domain_text, str):
            raise ValueError("domain rule names must be strings")
        domain = _cast_domain(domain_text)
        if not isinstance(raw_rule, Mapping):
            raise ValueError("domain rule config must be a mapping")
        domain_rules[domain] = DomainRuleConfig(
            domain=domain,
            corpus=_cast_corpus(_required_string(raw_rule, "corpus")),
            collection_name=_cast_collection(
                _required_string(raw_rule, "collection_name")
            ),
            keywords=_read_string_tuple(raw_rule, "keywords"),
            regex=_read_string_tuple(raw_rule, "regex"),
        )

    return DomainRoutingConfig(
        retrieval_score_min=_required_float(routing, "retrieval_score_min"),
        escalate_to_think_below=_required_float(routing, "escalate_to_think_below"),
        p95_routing_budget_ms=_required_float(routing, "p95_routing_budget_ms"),
        citation_weight=_required_float(routing, "citation_weight"),
        domain_rules=domain_rules,
    )


def route(
    query: str,
    state: SystemState,
    config: DomainRoutingConfig,
    scorer: ConfidenceScorer,
    question_id: str | None = None,
) -> RouteDecision:
    """Route an Agent-0 query using deterministic local policy only."""

    started_at = time.perf_counter()
    classification = classify_domain(query, question_id=question_id)
    if not state.qdrant_available:
        return _decision(
            started_at=started_at,
            route_name="local_chat",
            classification=classification,
            confidence_score=0.0,
            threshold_used="qdrant_available",
            reason_code="qdrant_unavailable",
            corpus="none",
            collection_name="none",
            fallback_reason="qdrant_unavailable",
        )
    if classification.domain == "unknown":
        return _decision(
            started_at=started_at,
            route_name="local_chat",
            classification=classification,
            confidence_score=0.0,
            threshold_used="domain_classifier",
            reason_code="no_domain_match",
            corpus="none",
            collection_name="none",
            fallback_reason="no_domain_match",
        )

    if classification.collection_name != "none":
        assert_collection_namespace(
            classification.collection_name,
            DUAL_CORPUS_COLLECTIONS,
        )
    confidence = scorer.score(
        query=query,
        classification=classification,
        state=state,
        config=config,
    )
    if confidence.score >= config.retrieval_score_min:
        return _decision(
            started_at=started_at,
            route_name="local_rag",
            classification=classification,
            confidence_score=confidence.score,
            threshold_used="retrieval_score_min",
            reason_code="retrieval_confident",
        )
    if confidence.score >= config.escalate_to_think_below:
        return _decision(
            started_at=started_at,
            route_name="local_think",
            classification=classification,
            confidence_score=confidence.score,
            threshold_used="escalate_to_think_below",
            reason_code="retrieval_uncertain",
        )
    return _decision(
        started_at=started_at,
        route_name="local_chat",
        classification=classification,
        confidence_score=confidence.score,
        threshold_used="escalate_to_think_below",
        reason_code="retrieval_low_confidence",
        corpus="none",
        collection_name="none",
        fallback_reason="retrieval_low_confidence",
    )


def validate_routing_against_golden_questions(
    *,
    config: DomainRoutingConfig | None = None,
    state: SystemState | None = None,
    scorer: ConfidenceScorer | None = None,
) -> GoldenRoutingGateResult:
    """Route A0-PR03 golden questions and measure corpus/collection accuracy."""

    active_config = config or load_domain_routing_config()
    active_state = state or SystemState(qdrant_available=True)
    active_scorer = scorer or FakeConfidenceScorer(
        default_score=active_config.retrieval_score_min
    )
    questions = tuple(question for question in load_all_golden_questions() if question.enabled)
    decisions: list[RouteDecision] = []
    passed = 0
    for question in questions:
        decision = route(
            question.text,
            active_state,
            active_config,
            active_scorer,
            question_id=question.question_id,
        )
        decisions.append(decision)
        if (
            decision.corpus == question.expected_corpus
            and decision.collection_name == question.expected_collection
            and decision.route == "local_rag"
        ):
            passed += 1

    total = len(questions)
    latencies = [decision.latency_ms for decision in decisions]
    return GoldenRoutingGateResult(
        total_questions=total,
        passed=passed,
        failed=total - passed,
        accuracy=_ratio(passed, total),
        p95_routing_ms=_percentile(latencies, 95),
        decisions=tuple(decisions),
    )


def route_dry_run_p95(
    *,
    config: DomainRoutingConfig | None = None,
    iterations: int = 100,
) -> float:
    """Return p95 routing latency for synthetic offline decisions."""

    if iterations <= 0:
        raise ValueError("iterations must be greater than zero")
    active_config = config or load_domain_routing_config()
    state = SystemState(qdrant_available=True)
    scorer = FakeConfidenceScorer(default_score=active_config.retrieval_score_min)
    queries = (
        "qual o estado atual do GW-07?",
        "como a Selic afeta a inflacao?",
        "o que e duration de renda fixa?",
        "como calcular o EBITDA?",
        "pergunta sem dominio conhecido",
    )
    latencies: list[float] = []
    for index in range(iterations):
        decision = route(
            queries[index % len(queries)],
            state,
            active_config,
            scorer,
        )
        latencies.append(decision.latency_ms)
    return _percentile(latencies, 95)


def route_counts(decisions: Sequence[RouteDecision]) -> dict[str, int]:
    """Return deterministic route-count metadata."""

    return dict(Counter(decision.route for decision in decisions))


def reason_code_counts(decisions: Sequence[RouteDecision]) -> dict[str, int]:
    """Return deterministic reason-code count metadata."""

    return dict(Counter(decision.reason_code for decision in decisions))


def _decision(
    *,
    started_at: float,
    route_name: RouteName,
    classification: DomainClassification,
    confidence_score: float,
    threshold_used: str,
    reason_code: str,
    corpus: CorpusName | None = None,
    collection_name: CollectionName | None = None,
    fallback_reason: str | None = None,
) -> RouteDecision:
    return RouteDecision(
        route=route_name,
        corpus=corpus or classification.corpus,
        domain=classification.domain,
        collection_name=collection_name or classification.collection_name,
        confidence_score=confidence_score,
        threshold_used=threshold_used,
        reason_code=reason_code,
        latency_ms=(time.perf_counter() - started_at) * 1000,
        fallback_reason=fallback_reason,
        routing_mode="deterministic",
    )


def _required_string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"agent0.domain_routing.{key} must be a non-empty string")
    return value.strip()


def _required_float(mapping: Mapping[str, Any], key: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"agent0.domain_routing.{key} must be a number")
    return float(value)


def _read_string_tuple(mapping: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = mapping.get(key, ())
    if not isinstance(value, list | tuple):
        raise ValueError(f"agent0.domain_routing.{key} must be a list")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"agent0.domain_routing.{key} must contain strings")
        values.append(item.strip())
    return tuple(values)


def _validate_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _validate_score(value: float, field_name: str) -> None:
    if not 0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between zero and one")


def _cast_domain(value: str) -> DomainName:
    if value not in ALLOWED_DOMAIN_NAMES:
        raise ValueError("domain is not allowed")
    return cast(DomainName, value)


def _cast_corpus(value: str) -> CorpusName:
    if value not in ALLOWED_CORPORA:
        raise ValueError("corpus is not allowed")
    return cast(CorpusName, value)


def _cast_collection(value: str) -> CollectionName:
    if value not in ALLOWED_COLLECTIONS:
        raise ValueError("collection_name is not allowed")
    return cast(CollectionName, value)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)
