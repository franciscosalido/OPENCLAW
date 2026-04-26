import unittest

from backend.rag.context_packer import RetrievedChunk
from backend.rag.prompt_builder import PromptBuilder


def chunk(doc_id: str = "doc-a", chunk_index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{doc_id}:{chunk_index}",
        score=0.87,
        doc_id=doc_id,
        chunk_index=chunk_index,
        text="Conteudo sintetico sobre Selic e renda fixa.",
        token_count=7,
        rank=1,
        payload={"source": "synthetic"},
    )


class PromptBuilderTests(unittest.TestCase):
    def test_factual_prompt_uses_no_think_and_citations(self) -> None:
        builder = PromptBuilder()

        messages = builder.build("Qual o impacto da Selic?", [chunk()])

        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("/no_think", messages[1]["content"])
        self.assertIn("[doc-a#0]", messages[1]["content"])
        self.assertIn("Qual o impacto da Selic?", messages[1]["content"])

    def test_thinking_prompt_uses_think_directive(self) -> None:
        builder = PromptBuilder()

        messages = builder.build(
            "Analise o contexto sintetico.",
            [chunk()],
            thinking_mode=True,
        )

        self.assertIn("/think", messages[1]["content"])
        self.assertNotIn("/no_think", messages[1]["content"])

    def test_zero_chunks_includes_insufficient_context_instruction(self) -> None:
        builder = PromptBuilder()

        messages = builder.build("Pergunta sem contexto?", [])

        self.assertIn("Nao ha contexto local recuperado", messages[1]["content"])
        self.assertIn("contexto local suficiente", messages[1]["content"])

    def test_multiple_chunks_are_separated_and_scored(self) -> None:
        builder = PromptBuilder()

        messages = builder.build(
            "Compare os trechos.",
            [chunk("doc-a", 0), chunk("doc-b", 2)],
        )

        user_content = messages[1]["content"]
        self.assertIn("[doc-a#0] (score: 0.870)", user_content)
        self.assertIn("[doc-b#2] (score: 0.870)", user_content)
        self.assertIn("---", user_content)

    def test_rejects_empty_question(self) -> None:
        builder = PromptBuilder()

        with self.assertRaises(ValueError):
            builder.build("  ", [chunk()])


if __name__ == "__main__":
    unittest.main()
