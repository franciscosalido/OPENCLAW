from __future__ import annotations

import hashlib
import unittest
from collections import Counter
from pathlib import Path

from backend.ingestion.bootstrap import manifest_path_for_corpus
from backend.ingestion.manifest import load_manifest, resolve_corpus_path


class DualCorpusManifestTests(unittest.TestCase):
    def test_internal_manifest_loads(self) -> None:
        manifest = load_manifest(manifest_path_for_corpus("internal"))

        self.assertGreaterEqual(len(manifest.documents), 5)
        self.assertTrue(
            all(document.ingestion_policy == "internal" for document in manifest.documents)
        )
        self.assertTrue(
            all(document.financial_domain is None for document in manifest.documents)
        )

    def test_financial_manifest_loads(self) -> None:
        manifest = load_manifest(manifest_path_for_corpus("financial"))

        self.assertEqual(len(manifest.documents), 9)
        self.assertTrue(
            all(document.ingestion_policy == "financial" for document in manifest.documents)
        )
        self.assertTrue(
            all(document.financial_domain is not None for document in manifest.documents)
        )

    def test_financial_has_three_docs_per_domain(self) -> None:
        manifest = load_manifest(manifest_path_for_corpus("financial"))

        counts = Counter(document.financial_domain for document in manifest.documents)

        self.assertEqual(counts["macroeconomia"], 3)
        self.assertEqual(counts["renda_fixa"], 3)
        self.assertEqual(counts["valuation"], 3)

    def test_manifest_paths_resolve_inside_data_corpus_and_are_not_symlinks(self) -> None:
        for corpus in ("internal", "financial"):
            manifest_path = manifest_path_for_corpus(corpus)
            manifest = load_manifest(manifest_path)
            for document in manifest.documents:
                with self.subTest(corpus=corpus, doc_id=document.doc_id):
                    resolved = resolve_corpus_path(manifest_path, document)
                    self.assertTrue(resolved.is_relative_to(Path("data/corpus").resolve()))
                    self.assertFalse(resolved.is_symlink())

    def test_expected_hashes_are_pinned_and_match_files(self) -> None:
        for corpus in ("internal", "financial"):
            manifest_path = manifest_path_for_corpus(corpus)
            manifest = load_manifest(manifest_path)
            for document in manifest.documents:
                with self.subTest(corpus=corpus, doc_id=document.doc_id):
                    resolved = resolve_corpus_path(manifest_path, document)
                    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()

                    self.assertIsNotNone(document.expected_hash)
                    self.assertEqual(document.expected_hash, digest)


if __name__ == "__main__":
    unittest.main()
