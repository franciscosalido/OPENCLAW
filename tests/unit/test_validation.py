import unittest

from backend.rag._validation import validate_question


class ValidationTests(unittest.TestCase):
    def test_validate_question_strips_text(self) -> None:
        self.assertEqual(validate_question("  pergunta sintetica  "), "pergunta sintetica")

    def test_validate_question_rejects_empty_text(self) -> None:
        with self.assertRaises(ValueError):
            validate_question("   ")

    def test_validate_question_rejects_non_string(self) -> None:
        with self.assertRaises(TypeError):
            validate_question(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
