"""Unit tests for the sparse vector contract."""

from __future__ import annotations

import math
import unittest

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

        self.assertEqual(vector.indices, [1])
        self.assertEqual(vector.values, [1.0])


if __name__ == "__main__":
    unittest.main()
