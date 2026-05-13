from __future__ import annotations

import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.agent0.golden_questions import (
    DEFAULT_FINANCIAL_QUESTIONS_PATH,
    DEFAULT_INTERNAL_QUESTIONS_PATH,
    GoldenManifest,
    GoldenQuestion,
    load_all_golden_questions,
    load_corpus_documents,
    load_golden_manifest,
    validate_expected_doc_ids,
)


GENERIC_FINANCIAL_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^o que [ée]\b", re.IGNORECASE),
    re.compile(r"^como [ée]\b", re.IGNORECASE),
    re.compile(r"^o que significa\b", re.IGNORECASE),
    re.compile(r"^defina\b", re.IGNORECASE),
    re.compile(r"^explique o que\b", re.IGNORECASE),
    re.compile(r"^como calcular\b", re.IGNORECASE),
    re.compile(r"^como .+ afeta\b", re.IGNORECASE),
)


class GoldenQuestionManifestTests(unittest.TestCase):
    MIN_FINANCIAL_QUESTIONS_PER_DOMAIN = 2
    MIN_FINANCIAL_QUERY_WORDS = 9

    def test_internal_manifest_loads(self) -> None:
        manifest = load_golden_manifest(DEFAULT_INTERNAL_QUESTIONS_PATH)

        self.assertEqual(len(manifest.questions), 5)
        self.assertTrue(
            all(question.question_id.startswith("iq-") for question in manifest.questions)
        )
        self.assertTrue(
            all(question.expected_corpus == "internal" for question in manifest.questions)
        )
        self.assertTrue(
            all(
                question.expected_collection == "openclaw_internal"
                for question in manifest.questions
            )
        )

    def test_internal_manifest_covers_all_internal_corpus_documents(self) -> None:
        manifest = load_golden_manifest(DEFAULT_INTERNAL_QUESTIONS_PATH)
        documents = load_corpus_documents()["internal"]
        enabled_doc_ids = {
            doc_id
            for question in manifest.questions
            if question.enabled
            for doc_id in question.expected_doc_ids
        }

        self.assertEqual(enabled_doc_ids, set(documents))

    def test_financial_manifest_loads(self) -> None:
        manifest = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)

        self.assertEqual(len(manifest.questions), 9)
        self.assertTrue(
            all(question.question_id.startswith("fq-") for question in manifest.questions)
        )
        self.assertTrue(
            all(question.expected_corpus == "financial" for question in manifest.questions)
        )
        self.assertTrue(
            all(
                question.expected_collection == "openclaw_financial"
                for question in manifest.questions
            )
        )

    def test_financial_queries_are_not_trivially_parametric(self) -> None:
        manifest = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)

        for question in manifest.questions:
            if not question.enabled:
                continue
            clean_text = question.text.strip()
            with self.subTest(question_id=question.question_id):
                for pattern in GENERIC_FINANCIAL_QUERY_PATTERNS:
                    self.assertIsNone(
                        pattern.match(clean_text),
                        f"{question.question_id}: '{clean_text}' matches "
                        f"parametric pattern '{pattern.pattern}'",
                    )
                word_count = len(clean_text.split())
                self.assertGreaterEqual(
                    word_count,
                    self.MIN_FINANCIAL_QUERY_WORDS,
                    f"{question.question_id}: '{clean_text}' has only "
                    f"{word_count} words",
                )

    def test_financial_manifest_covers_all_financial_corpus_documents(self) -> None:
        manifest = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)
        documents = load_corpus_documents()["financial"]
        enabled_doc_ids = {
            doc_id
            for question in manifest.questions
            if question.enabled
            for doc_id in question.expected_doc_ids
        }

        self.assertEqual(enabled_doc_ids, set(documents))

    def test_financial_manifest_has_minimum_domain_coverage(self) -> None:
        manifest = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)
        counts = Counter(
            question.domain for question in manifest.questions if question.enabled
        )

        for domain in ("renda_fixa", "valuation", "macroeconomia"):
            with self.subTest(domain=domain):
                self.assertGreaterEqual(
                    counts[domain],
                    self.MIN_FINANCIAL_QUESTIONS_PER_DOMAIN,
                )

    def test_financial_manifest_includes_required_specialized_topics(self) -> None:
        manifest = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)
        expected_doc_ids = {
            doc_id
            for question in manifest.questions
            for doc_id in question.expected_doc_ids
        }

        self.assertIn("financial_renda_fixa_risco_credito", expected_doc_ids)
        self.assertIn("financial_macro_balanco_riscos", expected_doc_ids)
        self.assertIn("financial_macro_expectativas", expected_doc_ids)
        self.assertIn("financial_valuation_custo_capital", expected_doc_ids)

    def test_financial_manifest_yaml_round_trips_stably(self) -> None:
        original = load_golden_manifest(DEFAULT_FINANCIAL_QUESTIONS_PATH)

        with tempfile.TemporaryDirectory() as tmpdir:
            roundtrip_path = Path(tmpdir) / "financial_questions.yaml"
            roundtrip_path.write_text(
                yaml.safe_dump(
                    {
                        "questions": [
                            question.model_dump(mode="json")
                            for question in original.questions
                        ]
                    },
                    allow_unicode=True,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            reloaded = load_golden_manifest(roundtrip_path)

        self.assertEqual(original, reloaded)

    def test_question_id_format_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            GoldenQuestion.model_validate({**_question(), "question_id": "bad-id"})

    def test_enabled_must_be_boolean(self) -> None:
        with self.assertRaises(ValidationError):
            GoldenQuestion.model_validate({**_question(), "enabled": "true"})

    def test_question_id_uniqueness_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            GoldenManifest.model_validate(
                {"questions": [_question(), _question()]},
            )

    def test_iq_cannot_point_to_financial_collection(self) -> None:
        with self.assertRaises(ValidationError):
            GoldenQuestion.model_validate(
                {
                    **_question(),
                    "expected_corpus": "financial",
                    "expected_collection": "openclaw_financial",
                }
            )

    def test_fq_cannot_point_to_internal_collection(self) -> None:
        with self.assertRaises(ValidationError):
            GoldenQuestion.model_validate(
                {
                    **_question(question_id="fq-001"),
                    "expected_corpus": "internal",
                    "expected_collection": "openclaw_internal",
                }
            )

    def test_expected_doc_ids_exist_in_corresponding_corpus_manifest(self) -> None:
        questions = load_all_golden_questions()
        documents = load_corpus_documents()

        validate_expected_doc_ids(questions, documents)

    def test_missing_expected_doc_id_raises_clear_error(self) -> None:
        question = GoldenQuestion.model_validate(
            {**_question(), "expected_doc_ids": ["missing_doc"]}
        )

        with self.assertRaisesRegex(ValueError, "question_id=iq-001.*missing_doc"):
            validate_expected_doc_ids([question], load_corpus_documents())

    def test_cross_manifest_question_ids_are_unique(self) -> None:
        questions = load_all_golden_questions()
        question_ids = [question.question_id for question in questions]

        self.assertEqual(len(question_ids), 14)
        self.assertEqual(len(question_ids), len(set(question_ids)))

    def test_duplicate_question_id_across_manifests_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            internal_path = Path(tmpdir) / "internal.yaml"
            financial_path = Path(tmpdir) / "financial.yaml"
            internal_path.write_text(
                "questions:\n"
                "  - question_id: iq-001\n"
                "    text: uma pergunta\n"
                "    expected_corpus: internal\n"
                "    expected_collection: openclaw_internal\n"
                "    expected_doc_ids: [internal_current_state]\n"
                "    domain: internal\n"
                "    language: pt-BR\n"
                "    enabled: true\n",
                encoding="utf-8",
            )
            financial_path.write_text(
                "questions:\n"
                "  - question_id: iq-001\n"
                "    text: outra pergunta\n"
                "    expected_corpus: internal\n"
                "    expected_collection: openclaw_internal\n"
                "    expected_doc_ids: [internal_decisions]\n"
                "    domain: internal\n"
                "    language: pt-BR\n"
                "    enabled: true\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_all_golden_questions(
                    internal_path=internal_path,
                    financial_path=financial_path,
                )


def _question(question_id: str = "iq-001") -> dict[str, object]:
    return {
        "question_id": question_id,
        "text": "qual o estado atual do GW-07?",
        "expected_corpus": "internal",
        "expected_collection": "openclaw_internal",
        "expected_doc_ids": ["internal_current_state"],
        "domain": "internal",
        "language": "pt-BR",
        "enabled": True,
    }


if __name__ == "__main__":
    unittest.main()
