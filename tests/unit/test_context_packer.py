import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.rag.context_packer import (
    ContextBudgetConfig,
    ContextPacker,
    RetrievedChunk,
    load_context_budget_config,
)


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
        payload={
            "source": "synthetic",
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}#{chunk_index}",
        },
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

    def test_context_budget_disabled_returns_identical_chunk_list(self) -> None:
        packer = ContextPacker(
            max_context_tokens=100,
            context_budget=ContextBudgetConfig(enabled=False, max_context_chunks=1),
        )
        items = [
            chunk("doc-a", 0, "primeiro trecho sintetico", 0.9),
            chunk("doc-a", 1, "segundo trecho sintetico", 0.8),
        ]

        packed = packer.pack(items)

        self.assertEqual(packed, items)
        self.assertFalse(packer.last_budget_result.enabled)
        self.assertFalse(packer.last_budget_result.applied)
        self.assertEqual(packer.last_budget_result.chunks_retrieved, 2)
        self.assertEqual(packer.last_budget_result.chunks_used, 2)
        self.assertEqual(packer.last_budget_result.chunks_dropped, 0)

    def test_context_budget_caps_whole_chunks_and_preserves_metadata(self) -> None:
        packer = ContextPacker(
            max_context_tokens=100,
            context_budget=ContextBudgetConfig(enabled=True, max_context_chunks=3),
        )
        items = [
            chunk("doc-a", index, f"trecho sintetico {index}", 1.0 - index / 10)
            for index in range(5)
        ]

        packed = packer.pack(items)

        self.assertEqual(len(packed), 3)
        self.assertEqual([item.chunk_index for item in packed], [0, 1, 2])
        self.assertEqual([item.citation_id for item in packed], ["doc-a#0", "doc-a#1", "doc-a#2"])
        self.assertEqual(packed[0].payload["doc_id"], "doc-a")
        self.assertEqual(packed[0].payload["chunk_id"], "doc-a#0")
        self.assertTrue(packer.last_budget_result.enabled)
        self.assertTrue(packer.last_budget_result.applied)
        self.assertEqual(packer.last_budget_result.chunks_retrieved, 5)
        self.assertEqual(packer.last_budget_result.chunks_used, 3)
        self.assertEqual(packer.last_budget_result.chunks_dropped, 2)
        self.assertEqual(packer.last_budget_result.max_context_chunks, 3)

    def test_context_budget_not_applied_when_under_cap(self) -> None:
        packer = ContextPacker(
            max_context_tokens=100,
            context_budget=ContextBudgetConfig(enabled=True, max_context_chunks=3),
        )
        items = [
            chunk("doc-a", 0, "primeiro trecho sintetico", 0.9),
            chunk("doc-a", 1, "segundo trecho sintetico", 0.8),
        ]

        packed = packer.pack(items)

        self.assertEqual(packed, items)
        self.assertTrue(packer.last_budget_result.enabled)
        self.assertFalse(packer.last_budget_result.applied)
        self.assertEqual(packer.last_budget_result.chunks_used, 2)
        self.assertEqual(packer.last_budget_result.chunks_dropped, 0)

    def test_context_budget_config_validation(self) -> None:
        self.assertFalse(ContextBudgetConfig().validated().enabled)
        self.assertEqual(ContextBudgetConfig().validated().max_context_chunks, 3)
        with self.assertRaises(ValueError):
            ContextBudgetConfig(enabled=True, max_context_chunks=0).validated()
        with self.assertRaises(ValueError):
            ContextBudgetConfig(mode="chars").validated()  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ContextBudgetConfig(apply_to_aliases=("local_chat",)).validated()

    def test_load_context_budget_config_reads_yaml(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(
                """
rag:
  context_budget:
    enabled: true
    max_context_chunks: 2
    mode: "whole_chunks"
    apply_to_aliases:
      - "local_rag"
""",
                encoding="utf-8",
            )

            config = load_context_budget_config(path)

        self.assertTrue(config.enabled)
        self.assertEqual(config.max_context_chunks, 2)
        self.assertEqual(config.apply_to_aliases, ("local_rag",))


if __name__ == "__main__":
    unittest.main()
