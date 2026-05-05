from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from scripts import run_golden_harness, run_rag_alias_comparison


FORBIDDEN_REPORT_KEYS = {
    "answer",
    "question",
    "prompt",
    "chunks",
    "chunk",
    "vectors",
    "vector",
    "payload",
    "qdrant_payload",
    "api_key",
    "authorization",
    "secret",
    "password",
    "headers",
    "raw_response",
    "raw_exception",
    "exception_message",
    "traceback",
}


def _config_file(
    tmp_path: Path,
    *,
    candidate_alias: str = "local_rag_fast",
    candidate_provider: str = "ollama",
    candidate_api_base: str = "http://localhost:11434",
    experimental_line: str = "      experimental: true\n",
) -> Path:
    path = tmp_path / "litellm_config.yaml"
    path.write_text(
        f"""
model_list:
  - model_name: local_rag
    litellm_params:
      model: ollama_chat/safe-baseline
      api_base: http://localhost:11434
      timeout: 60
    model_info:
      provider: ollama
      purpose: baseline
      thinking_mode: false
  - model_name: {candidate_alias}
    litellm_params:
      model: ollama_chat/safe-candidate
      api_base: {candidate_api_base}
      timeout: 60
    model_info:
      provider: {candidate_provider}
      purpose: candidate
{experimental_line}      thinking_mode: false
""",
        encoding="utf-8",
    )
    return path


async def _fake_runner(
    question: run_golden_harness.GoldenQuestion,
    alias: str,
    run_type: str,
) -> run_rag_alias_comparison.AliasComparisonResult:
    is_candidate = alias != "local_rag"
    return run_rag_alias_comparison.AliasComparisonResult(
        question_id=question.question_id,
        alias=alias,
        alias_role="candidate" if is_candidate else "baseline",
        experimental=is_candidate,
        run_type=run_type,
        total_ms=600.0 if is_candidate else 1000.0,
        generation_ms=300.0 if is_candidate else 600.0,
        prompt_eval_duration_ms=100.0,
        eval_duration_ms=250.0 if is_candidate else 500.0,
        eval_count=50,
        tokens_per_second=200.0,
        answer_length_chars=120,
        citation_present=True,
        fallback_applied=False,
        estimated_remote_tokens_avoided=42,
    )


class RagAliasComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_env_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            exit_code = await run_rag_alias_comparison.main_async(
                ["--candidate-alias", "local_rag_fast"],
            )

        self.assertEqual(exit_code, 2)

    def test_alias_validation_accepts_local_semantic_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(Path(tmpdir))
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        candidates = run_rag_alias_comparison.validate_aliases(
            baseline_alias="local_rag",
            candidate_aliases=("local_rag_fast",),
            alias_metadata=aliases,
        )

        self.assertEqual(candidates, ("local_rag_fast",))

    def test_alias_validation_rejects_remote_provider_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(
                Path(tmpdir),
                candidate_provider="openai",
                candidate_api_base="https://api.openai.com/v1",
            )
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        with self.assertRaises(ValueError):
            run_rag_alias_comparison.validate_aliases(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag_fast",),
                alias_metadata=aliases,
            )

    def test_alias_validation_rejects_env_api_base_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(
                Path(tmpdir),
                candidate_api_base="os.environ/OLLAMA_API_BASE",
            )
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        with self.assertRaises(ValueError):
            run_rag_alias_comparison.validate_aliases(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag_fast",),
                alias_metadata=aliases,
            )

    def test_alias_validation_rejects_concrete_model_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(Path(tmpdir))
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        for candidate in ("ollama_chat/qwen3:14b", "qwen3:14b"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    run_rag_alias_comparison.validate_aliases(
                        baseline_alias="local_rag",
                        candidate_aliases=(candidate,),
                        alias_metadata=aliases,
                    )

    def test_candidate_cannot_equal_baseline_and_baseline_remains_local_rag(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(Path(tmpdir))
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        with self.assertRaises(ValueError):
            run_rag_alias_comparison.validate_aliases(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag",),
                alias_metadata=aliases,
            )
        with self.assertRaises(ValueError):
            run_rag_alias_comparison.validate_aliases(
                baseline_alias="local_rag_fast",
                candidate_aliases=("local_rag",),
                alias_metadata=aliases,
            )

    def test_candidate_experimental_false_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_file(
                Path(tmpdir),
                experimental_line="      experimental: false\n",
            )
            aliases = run_rag_alias_comparison.load_alias_metadata(path)

        with self.assertRaises(ValueError):
            run_rag_alias_comparison.validate_aliases(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag_fast",),
                alias_metadata=aliases,
            )

    async def test_run_comparison_records_fixture_hash_and_writes_safe_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            config_path = _config_file(temp_path)
            jsonl_path, summary_path = await run_rag_alias_comparison.run_comparison(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag_fast",),
                litellm_config_path=config_path,
                output_dir=temp_path,
                runner=_fake_runner,
            )

            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        questions = run_golden_harness.load_questions()
        self.assertEqual(len(lines), len(questions) * 2)
        self.assertEqual(
            summary["question_fixture_hash"],
            run_rag_alias_comparison.question_fixture_hash(
                run_rag_alias_comparison.DEFAULT_QUESTIONS_PATH,
            ),
        )
        for line in lines:
            row = json.loads(line)
            self.assertTrue(FORBIDDEN_REPORT_KEYS.isdisjoint({key.lower() for key in row}))
            self.assertIn(row["alias_role"], {"baseline", "candidate"})
            self.assertEqual(row["run_type"], "warm_model")

    async def test_summary_separates_aliases_run_type_and_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            config_path = _config_file(temp_path)
            _jsonl_path, summary_path = await run_rag_alias_comparison.run_comparison(
                baseline_alias="local_rag",
                candidate_aliases=("local_rag_fast",),
                litellm_config_path=config_path,
                output_dir=temp_path,
                runner=_fake_runner,
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["baseline_alias"], "local_rag")
        self.assertEqual(summary["candidate_aliases"], ["local_rag_fast"])
        self.assertIn("warm_model", summary["results_by_alias"]["local_rag"])
        self.assertIn("warm_model", summary["results_by_alias"]["local_rag_fast"])
        self.assertEqual(
            summary["delta_by_candidate"]["local_rag_fast"]["total_ms_delta_pct"],
            40.0,
        )
        self.assertEqual(summary["citation_regression"]["local_rag_fast"], False)
        self.assertEqual(summary["hypothesis_supported"]["local_rag_fast"], True)

    def test_citation_regression_marks_hypothesis_unsupported(self) -> None:
        baseline = run_rag_alias_comparison.AliasComparisonResult(
            question_id="q1",
            alias="local_rag",
            alias_role="baseline",
            experimental=False,
            run_type="warm_model",
            total_ms=1000.0,
            generation_ms=600.0,
            prompt_eval_duration_ms=None,
            eval_duration_ms=None,
            eval_count=None,
            tokens_per_second=None,
            answer_length_chars=100,
            citation_present=True,
            fallback_applied=False,
            estimated_remote_tokens_avoided=10,
        )
        candidate = run_rag_alias_comparison.AliasComparisonResult(
            question_id="q1",
            alias="local_rag_fast",
            alias_role="candidate",
            experimental=True,
            run_type="warm_model",
            total_ms=500.0,
            generation_ms=300.0,
            prompt_eval_duration_ms=None,
            eval_duration_ms=None,
            eval_count=None,
            tokens_per_second=None,
            answer_length_chars=90,
            citation_present=False,
            fallback_applied=False,
            estimated_remote_tokens_avoided=10,
        )

        summary = run_rag_alias_comparison.build_summary(
            baseline_alias="local_rag",
            candidate_aliases=("local_rag_fast",),
            fixture_hash="hash",
            run_id="run",
            timestamp_utc="2026-05-04T00:00:00Z",
            results=(baseline, candidate),
        )

        citation_regression = cast(
            "dict[str, bool]",
            summary["citation_regression"],
        )
        hypothesis_supported = cast(
            "dict[str, bool]",
            summary["hypothesis_supported"],
        )

        self.assertEqual(citation_regression["local_rag_fast"], True)
        self.assertEqual(hypothesis_supported["local_rag_fast"], False)

    def test_warmup_is_discarded_from_measured_results(self) -> None:
        questions = run_golden_harness.load_questions()
        self.assertEqual(
            len(questions) * 2,
            len([1 for question in questions for _alias in ("local_rag", "fast")]),
        )
        summary = run_rag_alias_comparison.build_summary(
            baseline_alias="local_rag",
            candidate_aliases=("local_rag_fast",),
            fixture_hash="hash",
            run_id="run",
            timestamp_utc="2026-05-04T00:00:00Z",
            results=(),
        )
        self.assertEqual(summary["warmup_discarded"], True)

    def test_default_alias_constant_is_not_changed(self) -> None:
        self.assertEqual(run_rag_alias_comparison.DEFAULT_BASELINE_ALIAS, "local_rag")


if __name__ == "__main__":
    unittest.main()
