import unittest

from backend.rag.context_packer import ContextPacker, RetrievedChunk


def chunk(
    doc_id: str,
    chunk_index: int,
    text: str,
    score: float,
    token_count: int | None = None,
    rank: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{doc_id}:{chunk_index}",
        score=score,
        doc_id=doc_id,
        chunk_index=chunk_index,
        text=text,
        token_count=token_count or len(text.split()),
        rank=rank,
        payload={"source": "synthetic"},
    )


class ContextPackerTests(unittest.TestCase):
    def test_empty_chunks_returns_empty_list(self) -> None:
        packer = ContextPacker()

        self.assertEqual(packer.pack([]), [])

    def test_single_chunk_passes_through(self) -> None:
        packer = ContextPacker(max_context_tokens=20)
        item = chunk("doc-a", 0, "conteudo sintetico unico", 0.8)

        self.assertEqual(packer.pack([item]), [item])

    def test_dedup_removes_similar_and_keeps_higher_score(self) -> None:
        packer = ContextPacker(
            max_context_tokens=50,
            dedup_similarity_threshold=0.75,
        )
        lower_score = chunk(
            "doc-a",
            0,
            "Selic sintetica impacta renda fixa em cenario local",
            0.70,
            rank=1,
        )
        higher_score = chunk(
            "doc-a",
            1,
            "Selic sintetica impacta renda fixa no cenario local",
            0.91,
            rank=2,
        )
        different = chunk(
            "doc-b",
            0,
            "Rebalanceamento usa bandas de tolerancia",
            0.65,
            rank=3,
        )

        packed = packer.pack([lower_score, higher_score, different])

        self.assertEqual([item.id for item in packed], ["doc-a:1", "doc-b:0"])

    def test_token_limit_truncates_by_score_before_reordering(self) -> None:
        packer = ContextPacker(max_context_tokens=8)
        highest = chunk("doc-b", 3, "um dois tres quatro cinco", 0.95, token_count=5)
        second = chunk("doc-a", 1, "seis sete oito", 0.90, token_count=3)
        excluded = chunk("doc-a", 0, "nove dez onze", 0.80, token_count=3)

        packed = packer.pack([excluded, second, highest])

        self.assertEqual([item.id for item in packed], ["doc-a:1", "doc-b:3"])

    def test_reorder_by_document_position(self) -> None:
        packer = ContextPacker(max_context_tokens=50)
        later = chunk("doc-a", 2, "terceiro trecho", 0.95)
        earlier = chunk("doc-a", 0, "primeiro trecho", 0.70)
        middle = chunk("doc-a", 1, "segundo trecho", 0.80)

        packed = packer.pack([later, earlier, middle])

        self.assertEqual([item.chunk_index for item in packed], [0, 1, 2])

    def test_from_mapping_uses_payload_and_computes_token_count(self) -> None:
        item = RetrievedChunk.from_mapping(
            {
                "id": "point-1",
                "score": 0.88,
                "payload": {
                    "doc_id": "doc-a",
                    "chunk_index": 4,
                    "text": "texto sintetico com quatro tokens",
                    "security_level": "Level 2",
                },
            },
            rank=3,
        )

        self.assertEqual(item.id, "point-1")
        self.assertEqual(item.doc_id, "doc-a")
        self.assertEqual(item.chunk_index, 4)
        self.assertEqual(item.token_count, 5)
        self.assertEqual(item.rank, 3)
        self.assertEqual(item.citation_id, "doc-a#4")

    def test_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            ContextPacker(max_context_tokens=0)
        with self.assertRaises(ValueError):
            ContextPacker(dedup_similarity_threshold=1.5)
        with self.assertRaises(ValueError):
            RetrievedChunk.from_mapping(
                {
                    "score": 0.5,
                    "doc_id": "doc-a",
                    "chunk_index": -1,
                    "text": "texto",
                }
            )


if __name__ == "__main__":
    unittest.main()
