"""Analytic tests for pure retrieval evaluation metrics."""

from __future__ import annotations

import math
import unittest
from collections.abc import Sequence

from evaluation.eval_latency import latency_percentiles
from evaluation.eval_mrr import mean_reciprocal_rank, reciprocal_rank
from evaluation.eval_ndcg import dcg_at_k, ndcg_at_k
from evaluation.eval_precision import mean_precision_at_k, precision_at_k
from evaluation.eval_recall import mean_recall_at_k, recall_at_k


class PrecisionAtKTests(unittest.TestCase):
    """Grupo A: precision_at_k."""

    def test_precision_counts_relevant_top_k_slots(self) -> None:
        score = precision_at_k(["a", "b", "x"], frozenset({"a", "b"}), 3)
        self.assertAlmostEqual(score, 2.0 / 3.0)  # proof: 2 relevant hits / k=3.

    def test_precision_returns_zero_when_no_hits(self) -> None:
        score = precision_at_k(["x", "y"], frozenset({"a"}), 2)
        self.assertEqual(score, 0.0)  # proof: 0 relevant hits / k=2.

    def test_precision_returns_zero_for_empty_retrieved_ids(self) -> None:
        score = precision_at_k([], frozenset({"a"}), 3)
        self.assertEqual(score, 0.0)  # proof: empty retrieved list has 0 hits.

    def test_precision_counts_duplicate_doc_id_only_once(self) -> None:
        score = precision_at_k(["a", "a", "b"], frozenset({"a", "b"}), 3)
        self.assertAlmostEqual(score, 2.0 / 3.0)  # proof: unique hits {a,b} / k=3.

    def test_precision_duplicate_relevant_doc_does_not_accumulate_credit(self) -> None:
        score = precision_at_k(["a", "a", "a"], frozenset({"a"}), 3)
        self.assertAlmostEqual(score, 1.0 / 3.0)  # proof: unique hit {a} / k=3.

    def test_precision_denominator_is_k_when_fewer_results_are_returned(self) -> None:
        score = precision_at_k(["a"], frozenset({"a", "b"}), 4)
        self.assertAlmostEqual(score, 1.0 / 4.0)  # proof: 1 hit / requested k=4.

    def test_precision_canonical_denominator_k_case(self) -> None:
        score = precision_at_k(["a"], frozenset({"a"}), 5)
        self.assertAlmostEqual(score, 0.2)  # proof: 1 hit / k=5, denominator is k, not min(k, len(retrieved)).

    def test_precision_respects_cutoff(self) -> None:
        score = precision_at_k(["x", "a"], frozenset({"a"}), 1)
        self.assertEqual(score, 0.0)  # proof: top-1 is x, so 0 hits / k=1.

    def test_precision_rejects_zero_k(self) -> None:
        with self.assertRaises(ValueError):  # proof: k=0 is outside the valid cutoff domain.
            precision_at_k(["a"], frozenset({"a"}), 0)

    def test_precision_rejects_negative_k(self) -> None:
        with self.assertRaises(ValueError):  # proof: k=-1 is outside the valid cutoff domain.
            precision_at_k(["a"], frozenset({"a"}), -1)

    def test_precision_rejects_empty_expected_ids(self) -> None:
        with self.assertRaises(ValueError):  # proof: no ground truth means precision is undefined.
            precision_at_k(["a"], frozenset(), 1)

    def test_precision_expected_ids_are_unordered(self) -> None:
        score = precision_at_k(["b", "a"], frozenset({"a", "b"}), 2)
        self.assertEqual(score, 1.0)  # proof: 2 hits / k=2 regardless of expected set order.

    def test_precision_ignores_hits_after_cutoff(self) -> None:
        score = precision_at_k(["x", "y", "a"], frozenset({"a"}), 2)
        self.assertEqual(score, 0.0)  # proof: relevant a is rank 3, outside k=2.


class RecallAtKTests(unittest.TestCase):
    """Grupo B: recall_at_k."""

    def test_recall_counts_relevant_docs_found(self) -> None:
        score = recall_at_k(["a", "b", "x"], frozenset({"a", "b", "c"}), 3)
        self.assertAlmostEqual(score, 2.0 / 3.0)  # proof: found {a,b} / 3 relevant docs.

    def test_recall_can_reach_one_with_k_larger_than_result_count(self) -> None:
        score = recall_at_k(["a", "b"], frozenset({"a", "b"}), 5)
        self.assertEqual(score, 1.0)  # proof: found all 2 relevant docs / 2 expected docs.

    def test_recall_duplicate_doc_id_does_not_accumulate_credit(self) -> None:
        score = recall_at_k(["a", "a"], frozenset({"a", "b"}), 2)
        self.assertAlmostEqual(score, 1.0 / 2.0)  # proof: unique hit {a} / 2 expected docs.

    def test_recall_returns_zero_for_empty_retrieved_ids(self) -> None:
        score = recall_at_k([], frozenset({"a", "b"}), 2)
        self.assertEqual(score, 0.0)  # proof: empty retrieved list finds 0 of 2 relevant docs.

    def test_recall_returns_zero_when_no_hits(self) -> None:
        score = recall_at_k(["x", "y"], frozenset({"a", "b"}), 2)
        self.assertEqual(score, 0.0)  # proof: found 0 relevant docs / 2 expected docs.

    def test_recall_respects_cutoff(self) -> None:
        score = recall_at_k(["x", "a"], frozenset({"a"}), 1)
        self.assertEqual(score, 0.0)  # proof: relevant a is rank 2, outside k=1.

    def test_recall_rejects_non_positive_k(self) -> None:
        for invalid_k in (0, -2):
            with self.subTest(k=invalid_k):
                with self.assertRaises(ValueError):  # proof: valid recall cutoff requires k > 0.
                    recall_at_k(["a"], frozenset({"a"}), invalid_k)

    def test_recall_rejects_empty_expected_ids(self) -> None:
        with self.assertRaises(ValueError):  # proof: no ground truth means recall is undefined.
            recall_at_k(["a"], frozenset(), 1)


class ReciprocalRankTests(unittest.TestCase):
    """Grupo C: reciprocal_rank + mean_reciprocal_rank."""

    def test_reciprocal_rank_first_result_hit(self) -> None:
        score = reciprocal_rank(["a", "b"], frozenset({"a"}))
        self.assertEqual(score, 1.0)  # proof: first relevant rank is 1, so 1/1.

    def test_reciprocal_rank_second_result_hit(self) -> None:
        score = reciprocal_rank(["x", "a"], frozenset({"a"}))
        self.assertEqual(score, 0.5)  # proof: first relevant rank is 2, so 1/2.

    def test_reciprocal_rank_uses_raw_rank_with_duplicates(self) -> None:
        score = reciprocal_rank(["x", "x", "a"], frozenset({"a"}))
        self.assertAlmostEqual(score, 1.0 / 3.0)  # proof: first hit is at raw rank 3, so 1/3.

    def test_reciprocal_rank_returns_zero_without_hit(self) -> None:
        score = reciprocal_rank(["x", "y"], frozenset({"a"}))
        self.assertEqual(score, 0.0)  # proof: no relevant rank exists, convention is 0.

    def test_reciprocal_rank_returns_zero_for_empty_retrieved_ids(self) -> None:
        score = reciprocal_rank([], frozenset({"a"}))
        self.assertEqual(score, 0.0)  # proof: empty retrieved list has no relevant rank.

    def test_reciprocal_rank_rejects_empty_expected_ids(self) -> None:
        with self.assertRaises(ValueError):  # proof: no ground truth means first relevant rank is undefined.
            reciprocal_rank(["a"], frozenset())

    def test_mean_reciprocal_rank_averages_scores(self) -> None:
        score = mean_reciprocal_rank([1.0, 0.5, 0.0])
        self.assertEqual(score, 0.5)  # proof: (1 + 1/2 + 0) / 3 = 1.5 / 3.

    def test_mean_reciprocal_rank_accepts_single_zero(self) -> None:
        score = mean_reciprocal_rank([0.0])
        self.assertEqual(score, 0.0)  # proof: single score mean is the score itself, 0/1.

    def test_mean_reciprocal_rank_rejects_empty_scores(self) -> None:
        with self.assertRaises(ValueError):  # proof: mean denominator would be 0.
            mean_reciprocal_rank([])

    def test_mean_reciprocal_rank_rejects_negative_scores(self) -> None:
        with self.assertRaises(ValueError):  # proof: RR cannot be below 0 by definition.
            mean_reciprocal_rank([0.5, -0.1])

    def test_mean_reciprocal_rank_rejects_scores_above_one(self) -> None:
        with self.assertRaises(ValueError):  # proof: best possible RR is 1/1 = 1.
            mean_reciprocal_rank([1.1])

    def test_mean_reciprocal_rank_rejects_non_finite_scores(self) -> None:
        for invalid_score in (math.inf, -math.inf, math.nan):
            with self.subTest(score=invalid_score):
                with self.assertRaises(ValueError):  # proof: non-finite values cannot form a finite mean.
                    mean_reciprocal_rank([invalid_score])


class DcgNdcgTests(unittest.TestCase):
    """Grupo D: ndcg_at_k + dcg_at_k."""

    def test_dcg_single_relevance_grade_two(self) -> None:
        score = dcg_at_k([2.0], 1)
        self.assertEqual(score, 3.0)  # proof: (2^2 - 1) / log2(2) = 3 / 1.

    def test_dcg_two_ranked_scores(self) -> None:
        score = dcg_at_k([2.0, 1.0], 2)
        expected = 3.0 + (1.0 / math.log2(3.0))  # proof: rank1 gain 3 + rank2 gain 1/log2(3).
        self.assertAlmostEqual(score, expected)

    def test_dcg_respects_cutoff(self) -> None:
        score = dcg_at_k([2.0, 1.0], 1)
        self.assertEqual(score, 3.0)  # proof: k=1 keeps only rank1 gain 3/log2(2).

    def test_dcg_empty_relevance_scores_returns_zero(self) -> None:
        score = dcg_at_k([], 3)
        self.assertEqual(score, 0.0)  # proof: empty summation has value 0.

    def test_dcg_rejects_non_positive_k(self) -> None:
        with self.assertRaises(ValueError):  # proof: k=0 is not a valid DCG cutoff.
            dcg_at_k([1.0], 0)

    def test_dcg_rejects_negative_relevance(self) -> None:
        with self.assertRaises(ValueError):  # proof: graded relevance domain is non-negative.
            dcg_at_k([-1.0], 1)

    def test_ndcg_is_one_for_ideal_ranking(self) -> None:
        score = ndcg_at_k([2.0, 1.0], 2)
        self.assertEqual(score, 1.0)  # proof: actual DCG equals ideal DCG, so ratio is 1.

    def test_ndcg_penalizes_misordered_relevance(self) -> None:
        score = ndcg_at_k([1.0, 0.0, 2.0], 3)
        actual = 1.0 + 0.0 + (3.0 / 2.0)  # proof: 1/log2(2) + 0 + 3/log2(4).
        ideal = 3.0 + (1.0 / math.log2(3.0)) + 0.0  # proof: ideal order [2,1,0].
        self.assertAlmostEqual(score, actual / ideal)

    def test_ndcg_returns_zero_when_ideal_dcg_is_zero(self) -> None:
        score = ndcg_at_k([0.0, 0.0], 2)
        self.assertEqual(score, 0.0)  # proof: actual=0 and ideal=0, convention returns 0.

    def test_ndcg_with_fewer_scores_than_k_can_still_be_ideal(self) -> None:
        score = ndcg_at_k([1.0], 5)
        self.assertEqual(score, 1.0)  # proof: actual DCG 1 equals ideal DCG 1 despite k=5.


class LatencyPercentileTests(unittest.TestCase):
    """Grupo E: latency_percentiles."""

    def test_latency_percentile_median_odd_count(self) -> None:
        result = latency_percentiles([10.0, 20.0, 30.0], (50,))
        self.assertEqual(result, {50: 20.0})  # proof: rank=0.50*(3-1)=1, value index 1.

    def test_latency_percentile_median_even_count_interpolates(self) -> None:
        result = latency_percentiles([10.0, 20.0, 30.0, 40.0], (50,))
        self.assertEqual(result, {50: 25.0})  # proof: rank=1.5, so 20 + 0.5*(30-20).

    def test_latency_percentile_p95_two_values(self) -> None:
        result = latency_percentiles([0.0, 100.0], (95,))
        self.assertEqual(result, {95: 95.0})  # proof: rank=0.95, so 0 + 0.95*(100-0).

    def test_latency_p95_canonical_interpolation_case(self) -> None:
        result = latency_percentiles([10.0, 20.0, 30.0, 40.0, 100.0], (50, 95))
        # proof p50: rank=0.50*(5-1)=2.0, exact index 2, value 30.0.
        # proof p95: rank=0.95*(5-1)=3.8, lower=40, upper=100, weight=0.8, so 40+0.8*60=88.0.
        self.assertEqual(result, {50: 30.0, 95: 88.0})

    def test_latency_percentile_sorts_inputs(self) -> None:
        result = latency_percentiles([30.0, 10.0, 20.0], (50,))
        self.assertEqual(result, {50: 20.0})  # proof: sorted values [10,20,30], rank 1.

    def test_latency_percentile_single_sample_reused_for_all_percentiles(self) -> None:
        result = latency_percentiles([42.0])
        self.assertEqual(result, {50: 42.0, 95: 42.0, 99: 42.0})  # proof: n=1 makes every rank 0.

    def test_latency_percentile_zero_and_hundred_are_min_and_max(self) -> None:
        result = latency_percentiles([7.0, 3.0, 11.0], (0, 100))
        self.assertEqual(result, {0: 3.0, 100: 11.0})  # proof: rank 0 is min, rank n-1 is max.

    def test_latency_percentile_rejects_empty_latencies(self) -> None:
        with self.assertRaises(ValueError):  # proof: percentile rank needs n >= 1.
            latency_percentiles([])

    def test_latency_percentile_rejects_negative_percentile(self) -> None:
        with self.assertRaises(ValueError):  # proof: percentile -1 is outside [0,100].
            latency_percentiles([1.0], (-1,))

    def test_latency_percentile_rejects_percentile_above_hundred(self) -> None:
        with self.assertRaises(ValueError):  # proof: percentile 101 is outside [0,100].
            latency_percentiles([1.0], (101,))

    def test_latency_percentile_rejects_non_finite_latencies(self) -> None:
        for invalid_latency in (math.inf, -math.inf, math.nan):
            with self.subTest(latency=invalid_latency):
                with self.assertRaises(ValueError):  # proof: non-finite latency has no finite percentile.
                    latency_percentiles([1.0, invalid_latency])


class MetricInvariantTests(unittest.TestCase):
    """Grupo F: invariantes de monotonicidade e boundary."""

    def test_recall_is_monotonic_non_decreasing_with_larger_k(self) -> None:
        scores = [
            recall_at_k(["a", "x", "b"], frozenset({"a", "b"}), k)
            for k in (1, 2, 3)
        ]
        self.assertEqual(scores, [0.5, 0.5, 1.0])  # proof: hits are 1/2, 1/2, then 2/2.
        self.assertLessEqual(scores[0], scores[1])
        self.assertLessEqual(scores[1], scores[2])

    def test_dcg_is_monotonic_non_decreasing_for_non_negative_relevance(self) -> None:
        first = dcg_at_k([1.0, 2.0], 1)
        second = dcg_at_k([1.0, 2.0], 2)
        self.assertEqual(first, 1.0)  # proof: rank1 gain is (2^1 - 1) / log2(2) = 1.
        self.assertGreater(second, first)  # proof: rank2 has positive gain, so adding it increases DCG.

    def test_latency_percentiles_are_monotonic_non_decreasing(self) -> None:
        result = latency_percentiles([1.0, 2.0, 3.0, 4.0], (50, 95, 99))
        self.assertLessEqual(result[50], result[95])  # proof: sorted empirical quantiles preserve order.
        self.assertLessEqual(result[95], result[99])  # proof: p95 rank is below p99 rank.

    def test_precision_stays_within_unit_interval(self) -> None:
        scores = [
            precision_at_k(["a"], frozenset({"a"}), 1),
            precision_at_k(["x"], frozenset({"a"}), 1),
        ]
        self.assertEqual(scores, [1.0, 0.0])  # proof: possible hit counts are bounded by 0 and k.

    def test_recall_stays_within_unit_interval(self) -> None:
        scores = [
            recall_at_k(["a", "b"], frozenset({"a", "b"}), 2),
            recall_at_k(["x"], frozenset({"a", "b"}), 1),
        ]
        self.assertEqual(scores, [1.0, 0.0])  # proof: possible hit counts are bounded by 0 and expected size.

    def test_ndcg_stays_within_unit_interval_for_valid_scores(self) -> None:
        score = ndcg_at_k([1.0, 0.0, 2.0], 3)
        self.assertGreaterEqual(score, 0.0)  # proof: DCG and IDCG use non-negative gains.
        self.assertLessEqual(score, 1.0)  # proof: ideal DCG is the maximum ordering for same gains.


class MacroAverageTests(unittest.TestCase):
    """Grupo G: macro-averages."""

    def test_mean_precision_at_k_averages_query_scores(self) -> None:
        results: list[tuple[Sequence[str], frozenset[str]]] = [
            (["a"], frozenset({"a"})),
            (["x"], frozenset({"a"})),
        ]
        score = mean_precision_at_k(results, 1)
        self.assertEqual(score, 0.5)  # proof: per-query precision scores are 1 and 0; mean=(1+0)/2.

    def test_mean_recall_at_k_averages_query_scores(self) -> None:
        results: list[tuple[Sequence[str], frozenset[str]]] = [
            (["a"], frozenset({"a", "b"})),
            (["b", "c"], frozenset({"b", "c"})),
        ]
        score = mean_recall_at_k(results, 2)
        self.assertEqual(score, 0.75)  # proof: per-query recall scores are 1/2 and 1; mean=1.5/2.

    def test_mean_precision_at_k_rejects_empty_results(self) -> None:
        with self.assertRaises(ValueError):  # proof: macro precision mean denominator would be 0.
            mean_precision_at_k([], 1)

    def test_mean_recall_at_k_rejects_empty_results(self) -> None:
        with self.assertRaises(ValueError):  # proof: macro recall mean denominator would be 0.
            mean_recall_at_k([], 1)
