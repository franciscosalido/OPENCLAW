"""Unit tests for PR-11 dense-only versus hybrid comparator."""

from __future__ import annotations

import ast
import asyncio
import csv
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

import evaluation.compare_dense_vs_hybrid as comparator
from evaluation.compare_dense_vs_hybrid import (
    CSV_COLUMNS,
    CSV_SCHEMA_VERSION,
    EvalQuery,
    EvaluationRun,
    HybridDecisionThresholds,
    PhaseLatencies,
    QdrantConfigSnapshot,
    QueryCategory,
    QueryMetrics,
    RetrievalLikeResult,
    RetrievalMode,
    StaticRetrieverRunner,
    Verdict,
    assert_paired_query_metrics,
    assert_runs_comparable,
    bootstrap_ci,
    build_evaluation_run,
    build_query_rows,
    build_summary,
    category_breakdown,
    classify_retrieval_effect,
    compare_dense_vs_hybrid,
    dcg_at_k,
    decide_hybrid_promotion,
    default_eval_queries,
    delta_pair,
    format_terminal_summary,
    make_run_id,
    ndcg_at_k,
    percentile_interpolated,
    percentile_nearest_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    render_svg_dashboard,
    run_mode,
    write_all_outputs,
)


class FakeRunner:
    def __init__(self, results: dict[str, RetrievalLikeResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def retrieve(self, query: EvalQuery) -> RetrievalLikeResult:
        self.calls.append(query.query_id)
        return self.results[query.query_id]


class FakeSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        await asyncio.sleep(0)


class RankLike:
    def __init__(self, dense_rank: int | None, sparse_rank: int | None) -> None:
        self.dense_rank = dense_rank
        self.sparse_rank = sparse_rank


def q(
    query_id: str,
    *,
    category: QueryCategory = QueryCategory.LEXICAL,
    qrels: dict[str, int] | None = None,
) -> EvalQuery:
    return EvalQuery(
        query_id=query_id,
        text=f"synthetic query {query_id}",
        category=category,
        qrels={"doc-a": 2} if qrels is None else qrels,
    )


def retrieval(
    docs: Sequence[str],
    *,
    latency: float = 10.0,
    personality: str = "dense_only_baseline",
) -> RetrievalLikeResult:
    return RetrievalLikeResult(
        hit_doc_ids=tuple(docs),
        hit_result_ids=tuple(f"hit-{index}" for index, _doc in enumerate(docs)),
        phase_latencies=PhaseLatencies(
            embed_dense_ms=2.0,
            embed_sparse_ms=1.0 if personality != "dense_only_baseline" else 0.0,
            search_dense_ms=3.0,
            search_sparse_ms=2.0 if personality != "dense_only_baseline" else 0.0,
            fusion_ms=1.0 if personality != "dense_only_baseline" else 0.0,
            total_ms=latency,
        ),
        retrieval_personality=personality,
    )


def runs_and_metrics() -> tuple[
    EvaluationRun, EvaluationRun, list[QueryMetrics], list[QueryMetrics]
]:
    queries = (
        q("q1", qrels={"doc-a": 2, "doc-b": 0}),
        q("q2", category=QueryCategory.MACRO, qrels={"doc-c": 2, "doc-d": 1}),
        q("q3", category=QueryCategory.RISK, qrels={"doc-e": 2}),
    )
    timestamp = "2026-05-21T00:00:00+00:00"
    dense_run = build_evaluation_run(
        mode=RetrievalMode.DENSE_ONLY,
        queries=queries,
        model="local-rag",
        timestamp_iso=timestamp,
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name=None,
    )
    hybrid_run = build_evaluation_run(
        mode=RetrievalMode.HYBRID,
        queries=queries,
        model="local-rag",
        timestamp_iso=timestamp,
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name="default",
    )
    dense = [
        metric_for(
            queries[0],
            RetrievalMode.DENSE_ONLY,
            retrieval(("doc-b", "doc-x"), latency=8.0),
        ),
        metric_for(
            queries[1],
            RetrievalMode.DENSE_ONLY,
            retrieval(("doc-x", "doc-y"), latency=9.0),
        ),
        metric_for(
            queries[2],
            RetrievalMode.DENSE_ONLY,
            retrieval(("doc-x", "doc-y"), latency=10.0),
        ),
    ]
    hybrid = [
        metric_for(
            queries[0],
            RetrievalMode.HYBRID,
            retrieval(("doc-a", "doc-b"), latency=15.0, personality="lexical_boost"),
        ),
        metric_for(
            queries[1],
            RetrievalMode.HYBRID,
            retrieval(("doc-c", "doc-d"), latency=16.0, personality="agreement"),
        ),
        metric_for(
            queries[2],
            RetrievalMode.HYBRID,
            retrieval(
                ("doc-e", "doc-x"), latency=14.0, personality="sparse_only_rescue"
            ),
        ),
    ]
    return dense_run, hybrid_run, dense, hybrid


def metric_for(
    query: EvalQuery,
    mode: RetrievalMode,
    result: RetrievalLikeResult,
) -> QueryMetrics:
    return QueryMetrics(
        query_id=query.query_id,
        category=query.category,
        mode=mode,
        rank_1_doc_id=result.rank_1_doc_id,
        hit_doc_ids=result.hit_doc_ids,
        hit_result_ids=result.hit_result_ids,
        relevant_doc_ids=tuple(
            doc_id for doc_id, grade in query.qrels.items() if grade > 0
        ),
        precision_at_5=precision_at_k(result.hit_doc_ids, query.qrels, 5),
        recall_at_10=recall_at_k(result.hit_doc_ids, query.qrels, 10),
        mrr=reciprocal_rank(result.hit_doc_ids, query.qrels),
        ndcg_at_5=ndcg_at_k(result.hit_doc_ids, query.qrels, 5),
        latency_ms=result.latency_ms,
        retrieval_personality=result.retrieval_personality,
        phase_latencies=result.phase_latencies,
    )


def manual_metric(
    query_id: str,
    *,
    mode: RetrievalMode,
    ndcg: float,
    recall: float,
    latency: float,
    category: QueryCategory = QueryCategory.LEXICAL,
) -> QueryMetrics:
    return QueryMetrics(
        query_id=query_id,
        category=category,
        mode=mode,
        rank_1_doc_id="doc-a",
        hit_doc_ids=("doc-a",),
        hit_result_ids=(f"hit-{query_id}",),
        relevant_doc_ids=("doc-a",),
        precision_at_5=0.2,
        recall_at_10=recall,
        mrr=ndcg,
        ndcg_at_5=ndcg,
        latency_ms=latency,
        retrieval_personality="dense_only_baseline"
        if mode is RetrievalMode.DENSE_ONLY
        else "agreement",
        phase_latencies=PhaseLatencies(total_ms=latency),
    )


def test_precision_recall_mrr_and_dcg_metrics() -> None:
    qrels = {"a": 2, "b": 1, "c": 0}
    hits = ("c", "b", "a")

    assert precision_at_k(hits, qrels, 2) == pytest.approx(0.5)
    assert recall_at_k(hits, qrels, 10) == pytest.approx(1.0)
    assert reciprocal_rank(hits, qrels) == pytest.approx(0.5)
    assert dcg_at_k(("a",), qrels, 1) == pytest.approx(3.0)
    assert ndcg_at_k(("a", "b"), qrels, 2) == pytest.approx(1.0)
    assert ndcg_at_k(("x",), {"x": 0}, 1) == 0.0


def test_metric_edge_cases() -> None:
    assert precision_at_k((), {"a": 1}, 5) == 0.0
    assert recall_at_k(("x", "y"), {"a": 1}, 2) == 0.0
    assert reciprocal_rank((), {"a": 1}) == 0.0

    qrels = {"partial": 1, "full": 2}
    partial_first = ndcg_at_k(("partial", "full"), qrels, 2)
    full_first = ndcg_at_k(("full", "partial"), qrels, 2)
    assert partial_first < full_first


def test_percentiles_bootstrap_and_delta_pair_are_deterministic() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert percentile_nearest_rank(values, 95.0) == 4.0
    assert percentile_interpolated(values, 50.0) == pytest.approx(2.5)
    assert bootstrap_ci(values, n_resamples=25, rng_seed=7) == bootstrap_ci(
        values,
        n_resamples=25,
        rng_seed=7,
    )

    delta = delta_pair(0.5, 0.75, metric="recall_at_10")
    assert delta.absolute_delta == pytest.approx(0.25)
    assert delta.relative_delta_pct == pytest.approx(50.0)
    assert delta.winner == "hybrid"


def test_eval_query_validation_and_adversarial_empty_qrels() -> None:
    with pytest.raises(ValueError, match="query_id cannot be empty"):
        EvalQuery(
            query_id=" ", text="hello", category=QueryCategory.LEXICAL, qrels={"a": 1}
        )
    with pytest.raises(ValueError, match="text cannot contain null bytes"):
        EvalQuery(
            query_id="q", text="a\x00b", category=QueryCategory.LEXICAL, qrels={"a": 1}
        )
    with pytest.raises(ValueError, match="qrel grade"):
        EvalQuery(
            query_id="q", text="hello", category=QueryCategory.LEXICAL, qrels={"a": 3}
        )
    with pytest.raises(ValueError, match="non-adversarial"):
        EvalQuery(query_id="q", text="hello", category=QueryCategory.LEXICAL, qrels={})

    adversarial = EvalQuery(
        query_id="q_adv",
        text="fora do corpus",
        category=QueryCategory.ADVERSARIAL,
        qrels={},
    )
    assert adversarial.qrels == {}


def test_run_id_and_comparable_runs_guards() -> None:
    first = make_run_id("abc", RetrievalMode.DENSE_ONLY, "2026-05-21T00:00:00Z")
    second = make_run_id("abc", RetrievalMode.DENSE_ONLY, "2026-05-21T00:00:00Z")
    assert first == second

    dense_run, hybrid_run, _dense, _hybrid = runs_and_metrics()
    assert_runs_comparable(dense_run, hybrid_run)

    bad_corpus = EvaluationRun(
        run_id=hybrid_run.run_id,
        mode=RetrievalMode.HYBRID,
        corpus_hash="different",
        qdrant_snapshot_hash=None,
        model=hybrid_run.model,
        timestamp_iso=hybrid_run.timestamp_iso,
        query_count=hybrid_run.query_count,
        k_values=hybrid_run.k_values,
        search_top_k=hybrid_run.search_top_k,
        return_top_k=hybrid_run.return_top_k,
    )
    with pytest.raises(ValueError, match="corpus_hash"):
        assert_runs_comparable(dense_run, bad_corpus)

    bad_model = EvaluationRun(
        run_id=hybrid_run.run_id,
        mode=RetrievalMode.HYBRID,
        corpus_hash=hybrid_run.corpus_hash,
        qdrant_snapshot_hash=None,
        model="other",
        timestamp_iso=hybrid_run.timestamp_iso,
        query_count=hybrid_run.query_count,
        k_values=hybrid_run.k_values,
        search_top_k=hybrid_run.search_top_k,
        return_top_k=hybrid_run.return_top_k,
    )
    with pytest.raises(ValueError, match="model"):
        assert_runs_comparable(dense_run, bad_model)


@pytest.mark.asyncio
async def test_paired_guard_rejects_missing_dense_query_id() -> None:
    queries = (q("q1"), q("q2"))
    runner = FakeRunner({"q1": retrieval(("doc-a",))})

    run = build_evaluation_run(
        mode=RetrievalMode.DENSE_ONLY,
        queries=queries,
        model="m",
        timestamp_iso="2026-05-21T00:00:00+00:00",
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name=None,
    )

    with pytest.raises(KeyError):
        await run_mode(
            mode=RetrievalMode.DENSE_ONLY,
            queries=queries,
            runner=runner,
            run=run,
            cooldown_ms=0.0,
        )


@pytest.mark.asyncio
async def test_run_mode_computes_metrics_and_calls_cooldown() -> None:
    queries = (q("q1"), q("q2", qrels={"doc-b": 2}))
    runner = FakeRunner(
        {
            "q1": retrieval(("doc-a",), latency=7.0),
            "q2": retrieval(("doc-b",), latency=8.0),
        }
    )
    run = build_evaluation_run(
        mode=RetrievalMode.DENSE_ONLY,
        queries=queries,
        model="m",
        timestamp_iso="2026-05-21T00:00:00+00:00",
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name=None,
    )
    sleeper = FakeSleeper()

    metrics = await run_mode(
        mode=RetrievalMode.DENSE_ONLY,
        queries=queries,
        runner=runner,
        run=run,
        cooldown_ms=50.0,
        sleeper=sleeper,
    )

    assert [metric.query_id for metric in metrics] == ["q1", "q2"]
    assert metrics[0].mrr == 1.0
    assert sleeper.calls == [0.05]


def test_paired_query_metrics_guard_allows_order_mismatch_but_rejects_coverage() -> (
    None
):
    _dense_run, _hybrid_run, dense, hybrid = runs_and_metrics()
    assert_paired_query_metrics(dense, hybrid)
    assert_paired_query_metrics(dense, list(reversed(hybrid)))

    with pytest.raises(ValueError, match="identical query_id coverage"):
        assert_paired_query_metrics(dense, hybrid[:-1])


def test_paired_guard_rejects_duplicate_query_id_per_mode() -> None:
    _dense_run, _hybrid_run, dense, hybrid = runs_and_metrics()

    with pytest.raises(ValueError, match="duplicate query_id"):
        assert_paired_query_metrics([dense[0], dense[0]], hybrid)


def test_assert_runs_comparable_rejects_k_values_and_search_top_k_mismatch() -> None:
    dense_run, hybrid_run, _dense, _hybrid = runs_and_metrics()
    bad_k = EvaluationRun(
        run_id=hybrid_run.run_id,
        mode=RetrievalMode.HYBRID,
        corpus_hash=hybrid_run.corpus_hash,
        qdrant_snapshot_hash=None,
        model=hybrid_run.model,
        timestamp_iso=hybrid_run.timestamp_iso,
        query_count=hybrid_run.query_count,
        k_values=(3, 5),
        search_top_k=hybrid_run.search_top_k,
        return_top_k=hybrid_run.return_top_k,
    )
    with pytest.raises(ValueError, match="k_values"):
        assert_runs_comparable(dense_run, bad_k)

    bad_top_k = EvaluationRun(
        run_id=hybrid_run.run_id,
        mode=RetrievalMode.HYBRID,
        corpus_hash=hybrid_run.corpus_hash,
        qdrant_snapshot_hash=None,
        model=hybrid_run.model,
        timestamp_iso=hybrid_run.timestamp_iso,
        query_count=hybrid_run.query_count,
        k_values=hybrid_run.k_values,
        search_top_k=99,
        return_top_k=hybrid_run.return_top_k,
    )
    with pytest.raises(ValueError, match="search_top_k"):
        assert_runs_comparable(dense_run, bad_top_k)


def test_category_latency_personality_and_summary_verdict() -> None:
    dense_run, hybrid_run, dense, hybrid = runs_and_metrics()
    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="quimera_knowledge_v2"),
        bootstrap_resamples=20,
        generated_at_iso="2026-05-21T00:00:00+00:00",
    )

    assert (
        summary.aggregate_metrics_by_mode["hybrid"]["recall_at_10"]
        >= summary.aggregate_metrics_by_mode["dense_only"]["recall_at_10"]
    )
    assert (
        summary.latency_summary["hybrid"]["p95_ms"]
        >= summary.latency_summary["dense_only"]["p95_ms"]
    )
    assert summary.retrieval_personality_counts["lexical_boost"] == 1
    assert category_breakdown(dense, hybrid)["lexical"]["wins"] == 1.0
    assert decide_hybrid_promotion(summary).verdict in {
        Verdict.HYBRID_WINS,
        Verdict.INCONCLUSIVE,
        Verdict.NO_SIGNIFICANT_DIFFERENCE,
    }


def test_verdict_cases_hybrid_dense_no_significant_and_inconclusive() -> None:
    dense_run, hybrid_run, dense, hybrid = runs_and_metrics()
    hybrid_summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        thresholds=HybridDecisionThresholds(max_latency_p95_multiplier=3.0),
        bootstrap_resamples=20,
    )
    assert hybrid_summary.verdict.verdict is Verdict.HYBRID_WINS

    dense_wins_summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=hybrid,
        hybrid_metrics=dense,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        bootstrap_resamples=20,
    )
    assert dense_wins_summary.verdict.verdict is Verdict.DENSE_WINS

    no_diff = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=dense,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        bootstrap_resamples=20,
    )
    assert no_diff.verdict.verdict in {
        Verdict.INCONCLUSIVE,
        Verdict.NO_SIGNIFICANT_DIFFERENCE,
    }


def test_verdict_latency_p95_blocks_hybrid_promotion() -> None:
    dense_run, hybrid_run, _dense, _hybrid = runs_and_metrics()
    dense = [
        manual_metric(
            "q1", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
    ]
    hybrid = [
        manual_metric(
            "q1", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=100.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=100.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=100.0
        ),
    ]

    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        bootstrap_resamples=20,
    )

    assert summary.verdict.promote_hybrid is False
    assert summary.verdict.verdict is not Verdict.HYBRID_WINS


def test_verdict_dense_win_rate_blocks_hybrid_promotion() -> None:
    queries = tuple(q(f"q{i}") for i in range(1, 5))
    timestamp = "2026-05-21T00:00:00+00:00"
    dense_run = build_evaluation_run(
        mode=RetrievalMode.DENSE_ONLY,
        queries=queries,
        model="m",
        timestamp_iso=timestamp,
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name=None,
    )
    hybrid_run = build_evaluation_run(
        mode=RetrievalMode.HYBRID,
        queries=queries,
        model="m",
        timestamp_iso=timestamp,
        search_top_k=20,
        return_top_k=10,
        rrf_profile_name="default",
    )
    dense = [
        manual_metric(
            "q1", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.DENSE_ONLY, ndcg=0.9, recall=0.9, latency=10.0
        ),
        manual_metric(
            "q4", mode=RetrievalMode.DENSE_ONLY, ndcg=0.9, recall=0.9, latency=10.0
        ),
    ]
    hybrid = [
        manual_metric(
            "q1", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=12.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=12.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.HYBRID, ndcg=0.8, recall=0.8, latency=12.0
        ),
        manual_metric(
            "q4", mode=RetrievalMode.HYBRID, ndcg=0.8, recall=0.8, latency=12.0
        ),
    ]

    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        bootstrap_resamples=20,
    )

    assert summary.win_loss_tie["dense_wins"] == 2
    assert summary.verdict.promote_hybrid is False


def test_classify_retrieval_effect_all_personalities() -> None:
    assert classify_retrieval_effect(RankLike(None, 1)) == "sparse_only_rescue"
    assert classify_retrieval_effect(RankLike(1, None)) == "dense_only_rescue"
    assert classify_retrieval_effect(RankLike(3, 1)) == "lexical_boost"
    assert classify_retrieval_effect(RankLike(1, 3)) == "semantic_boost"
    assert classify_retrieval_effect(RankLike(2, 2)) == "agreement"


def test_csv_rows_and_writer_are_long_form_without_query_text(tmp_path: Path) -> None:
    dense_run, _hybrid_run, dense, _hybrid = runs_and_metrics()
    rows = build_query_rows(
        run=dense_run,
        metrics=dense,
        qdrant_snapshot=QdrantConfigSnapshot(
            collection_name="quimera_knowledge_v2",
            qdrant_server_version="1.13.2",
            qdrant_client_version="1.13.2",
        ),
    )
    csv_path = tmp_path / "rows.csv"

    comparator.write_csv(rows, csv_path)

    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        assert tuple(reader.fieldnames or ()) == CSV_COLUMNS
        materialized = list(reader)
    assert materialized[0]["schema_version"] == CSV_SCHEMA_VERSION
    assert "|" in materialized[0]["hit_doc_ids"]
    assert "synthetic query" not in csv_path.read_text(encoding="utf-8")


def test_json_markdown_svg_and_terminal_outputs_are_safe(tmp_path: Path) -> None:
    dense_run, hybrid_run, dense, hybrid = runs_and_metrics()
    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="quimera_knowledge_v2"),
        bootstrap_resamples=20,
    )

    paths = write_all_outputs(
        rows=[
            *build_query_rows(
                run=dense_run,
                metrics=dense,
                qdrant_snapshot=QdrantConfigSnapshot(
                    collection_name="quimera_knowledge_v2"
                ),
            ),
            *build_query_rows(
                run=hybrid_run,
                metrics=hybrid,
                qdrant_snapshot=QdrantConfigSnapshot(
                    collection_name="quimera_knowledge_v2"
                ),
            ),
        ],
        summary=summary,
        output_dir=tmp_path,
    )

    summary_payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert summary_payload["safety"] == {
        "includes_document_text": False,
        "includes_payload": False,
        "includes_query_text": False,
    }
    assert "verdict" in summary_payload

    svg = paths["svg"].read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "Quality Metrics" in svg
    assert "Latency p50/p95" in svg
    assert "Per-query NDCG@5 Delta" in svg
    assert "Category Breakdown" in svg
    assert "Retrieval Personality" in svg

    terminal = format_terminal_summary(summary)
    markdown = paths["markdown"].read_text(encoding="utf-8")
    combined = json.dumps(summary_payload) + svg + terminal + markdown
    assert "synthetic query" not in combined
    assert "chunk_text" not in combined
    assert "prompt" not in combined
    assert "answer" not in combined


def test_svg_zero_metric_values_and_negative_delta_render() -> None:
    dense_run, hybrid_run, _dense, _hybrid = runs_and_metrics()
    dense = [
        manual_metric(
            "q1", mode=RetrievalMode.DENSE_ONLY, ndcg=1.0, recall=1.0, latency=10.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.DENSE_ONLY, ndcg=0.0, recall=0.0, latency=10.0
        ),
    ]
    hybrid = [
        manual_metric(
            "q1", mode=RetrievalMode.HYBRID, ndcg=0.0, recall=0.0, latency=12.0
        ),
        manual_metric(
            "q2", mode=RetrievalMode.HYBRID, ndcg=0.0, recall=0.0, latency=12.0
        ),
        manual_metric(
            "q3", mode=RetrievalMode.HYBRID, ndcg=1.0, recall=1.0, latency=12.0
        ),
    ]

    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense,
        hybrid_metrics=hybrid,
        qdrant_snapshot=QdrantConfigSnapshot(collection_name="c"),
        bootstrap_resamples=20,
    )
    svg = render_svg_dashboard(summary)

    assert "<svg" in svg
    assert 'class="neg"' in svg
    assert "synthetic query" not in svg
    assert "document text" not in svg.casefold()


@pytest.mark.asyncio
async def test_compare_dense_vs_hybrid_end_to_end_with_fake_runners() -> None:
    queries = default_eval_queries()
    dense_runner, hybrid_runner = comparator.default_static_runners()

    rows, summary = await compare_dense_vs_hybrid(
        queries=queries,
        dense_runner=dense_runner,
        hybrid_runner=hybrid_runner,
        collection_name="quimera_knowledge_v2",
        bootstrap_resamples=20,
        timestamp_iso="2026-05-21T00:00:00+00:00",
    )

    assert len(rows) == len(queries) * 2
    assert summary.dense_run.corpus_hash == summary.hybrid_run.corpus_hash
    assert summary.verdict.promote_hybrid is True
    assert summary.win_loss_tie["hybrid_wins"] >= 1
    assert "<svg" in render_svg_dashboard(summary)


@pytest.mark.asyncio
async def test_static_runner_returns_empty_for_unknown_query() -> None:
    runner = StaticRetrieverRunner({})
    result = await runner.retrieve(q("unknown"))

    assert result.hit_doc_ids == ()
    assert result.retrieval_personality == "empty"


def test_main_dry_run_writes_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = asyncio.run(
        comparator.main(
            [
                "--collection",
                "quimera_knowledge_v2",
                "--output-dir",
                str(tmp_path),
                "--bootstrap-resamples",
                "20",
            ]
        )
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dense vs Hybrid Comparator" in captured.out
    assert (tmp_path / "dense_vs_hybrid_rows.csv").exists()
    assert (tmp_path / "dense_vs_hybrid_summary.json").exists()
    assert (tmp_path / "dense_vs_hybrid_report.md").exists()
    assert (tmp_path / "dense_vs_hybrid_charts.svg").exists()


def test_main_live_mode_is_explicitly_not_wired(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = asyncio.run(comparator.main(["--run-live"]))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "live mode is not wired" in captured.err


def test_include_debug_text_is_explicitly_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = asyncio.run(comparator.main(["--include-debug-text"]))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "debug text output is not supported" in captured.err


def test_script_static_imports_do_not_use_heavy_or_live_dependencies() -> None:
    source = Path(comparator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "qdrant_client",
        "numpy",
        "pandas",
        "scipy",
        "seaborn",
        "plotly",
        "matplotlib",
    }
    imported_roots: set[str] = set()
    call_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)

    assert imported_roots.isdisjoint(forbidden)
    assert "print" not in call_names


def test_comparator_does_not_call_collection_mutation_functions() -> None:
    source = Path(comparator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"create_collection", "delete_collection", "recreate_collection"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_forbidden_output_tokens_include_vector_family() -> None:
    tokens = set(comparator.FORBIDDEN_OUTPUT_TOKENS)

    assert {"vector", "dense_vector", "sparse_vector"}.issubset(tokens)


def test_unit_test_file_does_not_import_qdrant_client() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert "qdrant_client" not in imported_roots
