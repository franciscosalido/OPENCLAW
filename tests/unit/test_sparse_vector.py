"""Unit tests for the sparse vector contract."""

from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError
from typing import cast

from backend.rag.sparse_vector import SparseVector


class SparseVectorTests(unittest.TestCase):
    def test_sparse_vector_accepts_valid_indices_and_values(self) -> None:
        vector = SparseVector(indices=[3, 7], values=[1.5, 2.5])

        self.assertEqual(vector.nnz, 2)
        self.assertFalse(vector.is_empty())
        self.assertEqual(
            vector.to_qdrant_payload(),
            {"indices": [3, 7], "values": [1.5, 2.5]},
        )

    def test_sparse_vector_allows_empty_vector(self) -> None:
        vector = SparseVector(indices=[], values=[])

        self.assertEqual(vector.nnz, 0)
        self.assertTrue(vector.is_empty())

    def test_sparse_vector_rejects_mismatched_lengths(self) -> None:
        with self.assertRaisesRegex(ValueError, "len\\(indices\\) == len\\(values\\)"):
            SparseVector(indices=[1], values=[1.0, 2.0])

    def test_sparse_vector_rejects_negative_indices(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative"):
            SparseVector(indices=[1, -2], values=[1.0, 2.0])

    def test_sparse_vector_rejects_duplicate_indices(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            SparseVector(indices=[1, 1], values=[1.0, 2.0])

    def test_sparse_vector_rejects_non_finite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            SparseVector(indices=[1], values=[math.inf])

    def test_sparse_vector_copies_input_lists(self) -> None:
        indices = [1]
        values = [1.0]

        vector = SparseVector(indices=indices, values=values)
        indices.append(2)
        values.append(2.0)

        self.assertEqual(vector.indices, (1,))
        self.assertEqual(vector.values, (1.0,))

    def test_sparse_vector_payload_returns_defensive_lists(self) -> None:
        vector = SparseVector(indices=[1], values=[1.0])
        payload = vector.to_qdrant_payload()

        cast(list[int], payload["indices"]).append(2)
        cast(list[float], payload["values"]).append(2.0)

        self.assertEqual(vector.indices, (1,))
        self.assertEqual(vector.values, (1.0,))


class SparseVectorFrozenTests(unittest.TestCase):
    def test_sparse_vector_is_frozen(self) -> None:
        vector = SparseVector(indices=[1], values=[1.0])

        with self.assertRaises(FrozenInstanceError):
            vector.indices = [2]  # type: ignore[misc]

    def test_sparse_vector_equality_matches_same_payload(self) -> None:
        first = SparseVector(indices=[1, 2], values=[1.0, 2.0])
        second = SparseVector(indices=[1, 2], values=[1.0, 2.0])

        self.assertEqual(first, second)

    def test_sparse_vector_inequality_detects_different_indices(self) -> None:
        first = SparseVector(indices=[1, 2], values=[1.0, 2.0])
        second = SparseVector(indices=[1, 3], values=[1.0, 2.0])

        self.assertNotEqual(first, second)

    def test_sparse_vector_inequality_detects_different_values(self) -> None:
        first = SparseVector(indices=[1, 2], values=[1.0, 2.0])
        second = SparseVector(indices=[1, 2], values=[1.0, 3.0])

        self.assertNotEqual(first, second)

    def test_sparse_vector_is_hashable(self) -> None:
        vector = SparseVector(indices=[1, 2], values=[1.0, 2.0])

        self.assertEqual({vector}, {SparseVector(indices=[1, 2], values=[1.0, 2.0])})

    def test_sparse_vector_can_be_used_as_dict_key(self) -> None:
        vector = SparseVector(indices=[1, 2], values=[1.0, 2.0])
        lookup = {vector: "ok"}

        self.assertEqual(
            lookup[SparseVector(indices=[1, 2], values=[1.0, 2.0])],
            "ok",
        )


if __name__ == "__main__":
    unittest.main()
