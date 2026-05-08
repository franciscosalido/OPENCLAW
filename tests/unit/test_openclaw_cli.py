from __future__ import annotations

import json
import unittest
from io import StringIO
from unittest.mock import patch

from backend.agent0.golden_questions import Citation
from backend.agent0.openclaw import Answer
from scripts import openclaw as openclaw_cli


class OpenClawCliTests(unittest.TestCase):
    def test_cli_delegates_to_openclaw_ask(self) -> None:
        fake = _FakeOpenClaw()
        stdout = StringIO()

        with (
            patch.object(openclaw_cli, "OpenClaw", return_value=fake),
            patch("sys.stdout", stdout),
        ):
            exit_code = openclaw_cli.main(["ask", "qual o estado do GW-07?"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake.questions, ["qual o estado do GW-07?"])
        self.assertIn("Resposta local.", stdout.getvalue())

    def test_cli_json_output_safe(self) -> None:
        stdout = StringIO()
        with (
            patch.object(openclaw_cli, "OpenClaw", return_value=_FakeOpenClaw()),
            patch("sys.stdout", stdout),
        ):
            exit_code = openclaw_cli.main(["ask", "qual o estado do GW-07?", "--json"])

        data = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(data["answer"], "Resposta local.")
        self.assertNotIn("prompt", data)
        self.assertNotIn("chunks", data)
        self.assertNotIn("payload", data)

    def test_cli_errors_are_safe(self) -> None:
        stderr = StringIO()
        with (
            patch.object(openclaw_cli, "OpenClaw", side_effect=RuntimeError("boom")),
            patch("sys.stderr", stderr),
        ):
            exit_code = openclaw_cli.main(["ask", "qual o estado do GW-07?"])

        self.assertEqual(exit_code, 1)
        data = json.loads(stderr.getvalue())
        self.assertEqual(data, {"error_category": "runtimeerror"})


class _FakeOpenClaw:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str) -> Answer:
        self.questions.append(question)
        return Answer(
            answer="Resposta local.",
            citations=(
                Citation(
                    question_id="iq-001",
                    source_id="source",
                    doc_id="internal_current_state",
                    chunk_id="internal_current_state#0",
                    corpus="internal",
                    collection_name="openclaw_internal",
                    origin_path="docs/current_state.md",
                    score=1.0,
                    rank=1,
                    retrieval_mode="fake",
                    chunk_index=0,
                ),
            ),
            route="local_rag",
            corpus="internal",
            latency_ms=1.0,
            citation_present=True,
            fallback_reason=None,
            error_category=None,
        )


if __name__ == "__main__":
    unittest.main()
