import unittest

from backend.rag.chunking import Chunk, chunk_text


class ChunkingTests(unittest.TestCase):
    def test_short_text_returns_one_chunk(self) -> None:
        chunks = chunk_text("Primeiro documento sintetico.", max_tokens=10, overlap_tokens=2)

        self.assertEqual(
            chunks,
            [Chunk(text="Primeiro documento sintetico.", index=0, start_char=0, end_char=29)],
        )

    def test_long_text_returns_multiple_chunks_with_overlap(self) -> None:
        text = (
            "alfa beta gama delta.\n\n"
            "epsilon zeta eta theta.\n\n"
            "iota kappa lambda mu."
        )

        chunks = chunk_text(text, max_tokens=4, overlap_tokens=2)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].text, "alfa beta gama delta.")
        self.assertTrue(chunks[1].text.startswith("gama delta."))
        self.assertIn("epsilon zeta eta theta.", chunks[1].text)
        self.assertTrue(chunks[2].text.startswith("eta theta."))
        self.assertIn("iota kappa lambda mu.", chunks[2].text)

    def test_markdown_headers_lists_and_code_are_chunked(self) -> None:
        text = (
            "# Titulo\n\n"
            "- item um\n"
            "- item dois\n\n"
            "```python\n"
            "print('ola')\n"
            "```\n\n"
            "Paragrafo final."
        )

        chunks = chunk_text(text, max_tokens=5, overlap_tokens=1)

        self.assertGreaterEqual(len(chunks), 3)
        joined = "\n".join(chunk.text for chunk in chunks)
        self.assertIn("# Titulo", joined)
        self.assertIn("- item um", joined)
        self.assertIn("```python", joined)
        self.assertIn("print('ola')", joined)

    def test_portuguese_text_with_accents_abbreviations_and_decimal_commas(self) -> None:
        text = (
            "O Dr. Silva avaliou inflação de 4,25% no cenário sintético. "
            "A Selic ficou em 10,50%, sem carteira real."
        )

        chunks = chunk_text(text, max_tokens=6, overlap_tokens=0)
        joined = " ".join(chunk.text for chunk in chunks)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("Dr.", joined)
        self.assertIn("4,25%", joined)
        self.assertIn("10,50%", joined)
        self.assertIn("sintético", joined)

    def test_edge_cases_empty_text_and_single_paragraph(self) -> None:
        self.assertEqual(chunk_text("   \n\n  "), [])

        chunks = chunk_text("Um unico paragrafo sem quebra.", max_tokens=20, overlap_tokens=3)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "Um unico paragrafo sem quebra.")

    def test_rejects_invalid_options(self) -> None:
        invalid_options = [
            {"max_tokens": 0, "overlap_tokens": 0},
            {"max_tokens": 5, "overlap_tokens": -1},
            {"max_tokens": 5, "overlap_tokens": 5},
        ]

        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    chunk_text("texto sintetico", **options)


if __name__ == "__main__":
    unittest.main()
