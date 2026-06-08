"""Extended offline unit tests for PR-09 hybrid ingest script.

Complementa a suite principal (test_rag_ingest_hybrid.py — 53 testes) com
cobertura mais profunda em 8 seções:

  A. Segurança operacional — null bytes, whitespace attack, protected collections
  B. Conformidade de shape Qdrant — named vectors, UUID, traceabilidade
  C. Determinismo profundo — embedders determinísticos, ordem de batches, reingest
  D. Casos extremos — chunking de borda, sparse de borda, corpus edge cases
  E. Completude do summary — exact key set, rejeição de valores inválidos
  F. Invariantes estáticos — AST: sem uuid4, sem random, sem third-party
  G. Upload edge cases — zero points, batch ordering, batch_size=1
  H. Isolamento extrínseco — este arquivo não importa Qdrant, Docker, Ollama

Todos os testes são offline — nenhum requer Qdrant, Docker, Ollama ou Qwen3.

Autoria: COWORK / PR-09 deep review pass
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import scripts.rag_ingest_hybrid as ingest
from scripts.rag_ingest_hybrid import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_VERSION,
    DENSE_VECTOR_NAME,
    HYBRID_COLLECTION_NAME,
    LEGACY_COLLECTION_NAME,
    MAX_BATCH_SIZE,
    SPARSE_VECTOR_NAME,
    Chunk,
    Document,
    HybridIngestError,
    HybridIngestPoint,
    SparseVector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self._value = 0.0

    def perf_counter(self) -> float:
        self._value += 0.001
        return self._value


class FakeDenseEmbedder:
    def __init__(
        self,
        *,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        exc: Exception | None = None,
    ) -> None:
        self.dimensions = dimensions
        self.exc = exc
        self.calls: list[str] = []

    async def embed(self, text: str) -> Sequence[float]:
        self.calls.append(text)
        if self.exc is not None:
            raise self.exc
        return [0.1] * self.dimensions


class FakeSparseEmbedder:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self.exc = exc
        self.calls: list[str] = []

    async def embed(self, text: str) -> SparseVector:
        self.calls.append(text)
        if self.exc is not None:
            raise self.exc
        return SparseVector(indices=(1, 7), values=(1.0, 0.5))


class FakeUpsertClient:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self.exc = exc
        self.calls: list[tuple[str, list[HybridIngestPoint]]] = []

    async def upsert_points(
        self,
        *,
        collection_name: str,
        points: Sequence[HybridIngestPoint],
    ) -> None:
        if self.exc is not None:
            raise self.exc
        self.calls.append((collection_name, list(points)))


def _make_chunk(
    doc_id: str = "doc-x",
    text: str = "safe text for testing",
    chunk_index: int = 0,
) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        chunk_id=ingest.make_chunk_id(doc_id, chunk_index, text),
        chunk_index=chunk_index,
        text=text,
        source="unit",
    )


def _one_point(dimensions: int = 3) -> HybridIngestPoint:
    """Produce a single valid HybridIngestPoint with the given dense dimensions."""
    return ingest.prepare_hybrid_points(
        chunks=[_make_chunk()],
        dense_vectors=[[0.1] * dimensions],
        sparse_vectors=[SparseVector(indices=(5,), values=(1.0,))],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=dimensions,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
    )[0]


def _production_source() -> str:
    return Path(ingest.__file__).read_text(encoding="utf-8")


def _production_ast() -> ast.Module:
    return ast.parse(_production_source())


# ===========================================================================
# A. SEGURANÇA OPERACIONAL
# ===========================================================================


def test_collection_whitespace_strips_to_legacy_and_is_blocked() -> None:
    """`' quimera_knowledge '` strips to `'quimera_knowledge'` → PROTECTED → blocked.

    Garante que whitespace-padding não bypassa a proteção da collection legada.
    """
    with pytest.raises(HybridIngestError, match="protected"):
        ingest.assert_collection_is_safe_for_ingest(" quimera_knowledge ")


def test_collection_tab_newline_strips_to_legacy_and_is_blocked() -> None:
    r"""'\tquimera_knowledge\n' strips to legacy → blocked."""
    with pytest.raises(HybridIngestError, match="protected"):
        ingest.assert_collection_is_safe_for_ingest("\tquimera_knowledge\n")


def test_collection_null_byte_raises_value_error_not_ingest_error() -> None:
    """`'quimera_knowledge\\x00v2'` raises ValueError (null-byte check), not HybridIngestError.

    A ValueError sai de _validate_text antes de chegar à proteção de collection.
    """
    with pytest.raises(ValueError, match="null byte"):
        ingest.assert_collection_is_safe_for_ingest("quimera_knowledge\x00v2")


def test_collection_uppercase_variant_is_not_protected() -> None:
    """Case-sensitivity: 'QUIMERA_KNOWLEDGE' (uppercase) is NOT in PROTECTED_COLLECTIONS.

    Este teste documenta o contrato explicitamente: a proteção é case-sensitive.
    """
    result = ingest.assert_collection_is_safe_for_ingest("QUIMERA_KNOWLEDGE")
    assert result == "QUIMERA_KNOWLEDGE"


def test_document_null_byte_in_doc_id_raises() -> None:
    with pytest.raises(ValueError, match="null byte"):
        Document(doc_id="doc\x00a", text="safe text")


def test_document_null_byte_in_text_raises() -> None:
    with pytest.raises(ValueError, match="null byte"):
        Document(doc_id="doc-a", text="text\x00injection")


def test_document_null_byte_in_source_raises() -> None:
    with pytest.raises(ValueError, match="null byte"):
        Document(doc_id="doc-a", text="safe", source="src\x00evil")


def test_document_empty_source_raises() -> None:
    with pytest.raises(ValueError, match="source cannot be empty"):
        Document(doc_id="doc-a", text="safe", source="   ")


def test_chunk_negative_chunk_index_raises() -> None:
    with pytest.raises(ValueError, match="chunk_index must be non-negative"):
        Chunk(
            doc_id="doc-a",
            chunk_id="c",
            chunk_index=-1,
            text="abc",
            source="unit",
        )


def test_chunk_bool_chunk_index_raises() -> None:
    """chunk_index=True would be silently accepted as 1 without the bool guard."""
    with pytest.raises(TypeError, match="chunk_index must be an integer"):
        Chunk(
            doc_id="doc-a",
            chunk_id="c",
            chunk_index=True,  # bool is subclass of int — guard in __post_init__ catches it
            text="abc",
            source="unit",
        )


def test_validate_embedding_metadata_empty_model_raises() -> None:
    with pytest.raises(ValueError, match="embedding_model cannot be empty"):
        ingest.validate_embedding_metadata(
            embedding_model="   ",
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
            dense_vector_name=DENSE_VECTOR_NAME,
            sparse_vector_name=SPARSE_VECTOR_NAME,
        )


def test_validate_embedding_metadata_null_byte_in_version_raises() -> None:
    with pytest.raises(ValueError, match="null byte"):
        ingest.validate_embedding_metadata(
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            embedding_version="v1\x00injected",
            dense_vector_name=DENSE_VECTOR_NAME,
            sparse_vector_name=SPARSE_VECTOR_NAME,
        )


def test_validate_embedding_metadata_zero_dimensions_raises() -> None:
    with pytest.raises(ValueError, match="embedding_dimensions must be >= 1"):
        ingest.validate_embedding_metadata(
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=0,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
            dense_vector_name=DENSE_VECTOR_NAME,
            sparse_vector_name=SPARSE_VECTOR_NAME,
        )


async def test_execute_with_zero_points_never_calls_upsert() -> None:
    """dry_run=False com lista de pontos vazia → loop não executa → 0 chamadas ao client."""
    client = FakeUpsertClient()
    sent, batches, _ = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=[],
        batch_size=DEFAULT_BATCH_SIZE,
        dry_run=False,
        clock=FakeClock(),
    )
    assert sent == 0
    assert batches == 0
    assert client.calls == []


def test_main_missing_corpus_flag_returns_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main sem --synthetic e sem --corpus-path → exit 2."""
    exit_code = ingest.main([])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_max_chunks_zero_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    """--max-chunks 0 é rejeitado por _validate_optional_positive_int."""
    exit_code = ingest.main(["--synthetic", "--max-chunks", "0"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_embedding_dimensions_zero_returns_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--embedding-dimensions 0 é rejeitado por _validate_positive_int."""
    exit_code = ingest.main(["--synthetic", "--embedding-dimensions", "0"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_stderr_format_is_class_name_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Formato do stderr: exatamente 'hybrid ingest failed: <ClassName>'.

    Verifica que o output de erro nunca vaza o conteúdo da mensagem da exceção,
    apenas o nome da classe.
    """
    exit_code = ingest.main(["--collection", LEGACY_COLLECTION_NAME, "--synthetic"])
    captured = capsys.readouterr()
    assert exit_code == 2
    lines = captured.err.strip().splitlines()
    assert len(lines) == 1, f"Expected 1 stderr line, got: {lines!r}"
    assert lines[0].startswith("hybrid ingest failed: ")
    class_name = lines[0].removeprefix("hybrid ingest failed: ")
    assert class_name.isidentifier(), f"Not a valid Python identifier: {class_name!r}"
    # The collection name must NOT appear in any error output
    assert LEGACY_COLLECTION_NAME not in captured.err


def test_main_stdout_is_empty_on_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Em caso de erro, stdout deve estar vazio — nenhum JSON parcial é emitido."""
    exit_code = ingest.main(["--collection", LEGACY_COLLECTION_NAME, "--synthetic"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out.strip() == ""


# ===========================================================================
# B. CONFORMIDADE DE SHAPE QDRANT
# ===========================================================================


def test_point_id_is_a_valid_uuid_string() -> None:
    """point_id deve ser um UUID string válido (Qdrant aceita UUID como ponto ID)."""
    point = _one_point()
    parsed = uuid.UUID(point.point_id)  # levanta ValueError se inválido
    assert str(parsed) == point.point_id


def test_point_id_equals_chunk_id_in_payload() -> None:
    """point_id e payload['chunk_id'] devem ser iguais para rastreabilidade.

    O HybridRetriever do PR-08 usa payload.chunk_id para proveniência — este
    contrato deve ser mantido no ingest.
    """
    point = _one_point()
    assert point.point_id == point.payload["chunk_id"]


def test_qdrant_vector_dict_has_exactly_dense_and_sparse_keys() -> None:
    point = _one_point()
    d = point.to_qdrant_vector_dict()
    assert set(d.keys()) == {"dense", "sparse"}


def test_qdrant_vector_dict_dense_is_list_of_floats() -> None:
    point = _one_point(dimensions=4)
    d = point.to_qdrant_vector_dict()
    dense = d["dense"]
    assert isinstance(dense, list)
    assert all(isinstance(v, float) for v in dense)
    assert len(dense) == 4


def test_qdrant_vector_dict_sparse_has_indices_and_values() -> None:
    point = _one_point()
    d = point.to_qdrant_vector_dict()
    sparse = d["sparse"]
    assert isinstance(sparse, dict)
    assert set(sparse.keys()) == {"indices", "values"}
    assert isinstance(sparse["indices"], list)
    assert isinstance(sparse["values"], list)
    assert len(sparse["indices"]) == len(sparse["values"])


def test_qdrant_vector_dict_sparse_indices_are_ints() -> None:
    """Qdrant exige list[int] para sparse indices."""
    point = _one_point()
    d = point.to_qdrant_vector_dict()
    sparse = d["sparse"]
    assert isinstance(sparse, dict)
    for idx in sparse["indices"]:
        assert isinstance(idx, int)


def test_qdrant_vector_dict_sparse_values_are_floats() -> None:
    """Qdrant exige list[float] para sparse values."""
    point = _one_point()
    d = point.to_qdrant_vector_dict()
    sparse = d["sparse"]
    assert isinstance(sparse, dict)
    for val in sparse["values"]:
        assert isinstance(val, float)


def test_payload_contains_doc_id_for_retriever_traceability() -> None:
    """payload['doc_id'] é necessário para o HybridRetriever fazer proveniência."""
    point = _one_point()
    assert "doc_id" in point.payload
    assert isinstance(point.payload["doc_id"], str)


def test_payload_schema_version_matches_module_constant() -> None:
    """payload['schema_version'] deve ser igual a SCHEMA_VERSION do módulo."""
    point = _one_point()
    assert point.payload["schema_version"] == ingest.SCHEMA_VERSION


def test_dense_vector_name_in_payload_matches_constant() -> None:
    point = _one_point()
    assert point.payload["dense_vector_name"] == DENSE_VECTOR_NAME


def test_sparse_vector_name_in_payload_matches_constant() -> None:
    point = _one_point()
    assert point.payload["sparse_vector_name"] == SPARSE_VECTOR_NAME


def test_payload_embedding_dimensions_is_int_greater_than_zero() -> None:
    point = _one_point()
    dims = point.payload["embedding_dimensions"]
    assert isinstance(dims, int)
    assert dims > 0


# ===========================================================================
# C. DETERMINISMO PROFUNDO
# ===========================================================================


async def test_deterministic_dense_embedder_same_input_same_output() -> None:
    embedder = ingest._DeterministicDenseEmbedder()
    v1 = await embedder.embed("test text")
    v2 = await embedder.embed("test text")
    assert list(v1) == list(v2)


async def test_deterministic_dense_embedder_different_input_different_output() -> None:
    embedder = ingest._DeterministicDenseEmbedder()
    v1 = await embedder.embed("text A")
    v2 = await embedder.embed("text B")
    assert list(v1) != list(v2)


async def test_deterministic_dense_embedder_values_in_range() -> None:
    """Todos os valores de _DeterministicDenseEmbedder devem estar em [-1.0, 1.0]."""
    embedder = ingest._DeterministicDenseEmbedder()
    v = list(await embedder.embed("range check"))
    out_of_range = [x for x in v if not (-1.0 <= x <= 1.0)]
    assert not out_of_range, (
        f"{len(out_of_range)} values outside [-1.0, 1.0]: {out_of_range[:5]}"
    )


async def test_deterministic_dense_embedder_exact_dimensions() -> None:
    embedder = ingest._DeterministicDenseEmbedder()
    v = list(await embedder.embed("dimension check"))
    assert len(v) == DEFAULT_EMBEDDING_DIMENSIONS


async def test_deterministic_sparse_embedder_same_input_same_output() -> None:
    embedder = ingest._DeterministicSparseEmbedder()
    s1 = await embedder.embed("test text")
    s2 = await embedder.embed("test text")
    assert s1.indices == s2.indices
    assert s1.values == s2.values


async def test_deterministic_sparse_embedder_different_input_different_output() -> None:
    embedder = ingest._DeterministicSparseEmbedder()
    s1 = await embedder.embed("text A")
    s2 = await embedder.embed("text B")
    assert (s1.indices != s2.indices) or (s1.values != s2.values)


async def test_deterministic_sparse_embedder_output_is_valid_sparse_vector() -> None:
    """Saída de _DeterministicSparseEmbedder deve ser aceita por validate_sparse_vector."""
    embedder = ingest._DeterministicSparseEmbedder()
    sv = await embedder.embed("some text")
    validated = ingest.validate_sparse_vector(sv)
    assert validated.indices == sv.indices
    assert validated.values == sv.values


async def test_deterministic_sparse_embedder_indices_are_unique() -> None:
    """Embedder demo não deve produzir índices duplicados."""
    embedder = ingest._DeterministicSparseEmbedder()
    sv = await embedder.embed("duplicate guard")
    assert len(set(sv.indices)) == len(sv.indices)


def test_batched_preserves_element_order_across_all_batches() -> None:
    """batched deve emitir os itens na mesma ordem do input, sem transposição."""
    items = list(range(20))
    result: list[int] = []
    for batch in ingest.batched(items, 3):
        result.extend(batch)
    assert result == items


def test_batched_five_items_two_per_batch_exact_pattern() -> None:
    """5 itens, batch_size=2 → [[i0,i1],[i2,i3],[i4]]."""
    items = ["a", "b", "c", "d", "e"]
    batches = list(ingest.batched(items, 2))
    assert batches == [["a", "b"], ["c", "d"], ["e"]]


def test_chunk_document_chunk_indices_are_zero_based_contiguous() -> None:
    """chunk_index deve ser 0-based e contíguo em qualquer chunking."""
    document = Document(doc_id="doc-order", text="x" * 5000)
    chunks = ingest.chunk_document(document, max_chars=100)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


async def test_run_ingest_point_order_matches_chunk_order() -> None:
    """Pontos enviados ao client devem seguir a mesma ordem que os chunks gerados."""
    client = FakeUpsertClient()
    text = " ".join(f"word{i}" for i in range(500))
    documents = [Document(doc_id="doc-order-test", text=text, source="unit")]

    await ingest.run_ingest(
        documents=documents,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=client,
        dry_run=False,
        batch_size=DEFAULT_BATCH_SIZE,
        clock=FakeClock(),
    )
    sent_ids: list[str] = [p.point_id for _, batch in client.calls for p in batch]

    # Regenerar a ordem esperada de forma independente
    expected_chunks: list[Chunk] = []
    for doc in documents:
        expected_chunks.extend(ingest.chunk_document(doc))
    expected_ids = [c.chunk_id for c in expected_chunks]

    assert sent_ids == expected_ids


async def test_reingest_same_corpus_produces_same_point_ids() -> None:
    """Reingest com o mesmo corpus deve produzir os mesmos point_ids (idempotência de IDs)."""
    client_a = FakeUpsertClient()
    client_b = FakeUpsertClient()
    document = Document(doc_id="doc-reingest", text="abcdefghij" * 100, source="unit")

    for client in (client_a, client_b):
        await ingest.run_ingest(
            documents=[document],
            dense_embedder=FakeDenseEmbedder(),
            sparse_embedder=FakeSparseEmbedder(),
            upsert_client=client,
            dry_run=False,
            max_chunks=3,
            batch_size=10,
            clock=FakeClock(),
        )

    ids_a = [p.point_id for _, batch in client_a.calls for p in batch]
    ids_b = [p.point_id for _, batch in client_b.calls for p in batch]
    assert ids_a == ids_b, "Reingest produziu point_ids diferentes para o mesmo corpus"


# ===========================================================================
# D. CASOS EXTREMOS
# ===========================================================================


def test_batched_empty_sequence_yields_nothing() -> None:
    assert list(ingest.batched([], DEFAULT_BATCH_SIZE)) == []


def test_batched_single_item_in_single_batch() -> None:
    assert list(ingest.batched(["only"], 100)) == [["only"]]


def test_batched_exact_max_batch_size_is_one_batch() -> None:
    items = list(range(MAX_BATCH_SIZE))
    batches = list(ingest.batched(items, MAX_BATCH_SIZE))
    assert len(batches) == 1
    assert len(batches[0]) == MAX_BATCH_SIZE


def test_chunk_document_text_exactly_max_chars_produces_one_chunk() -> None:
    text = "a" * 100
    document = Document(doc_id="doc-exact", text=text)
    chunks = ingest.chunk_document(document, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_document_text_max_chars_plus_one_produces_two_chunks() -> None:
    text = "a" * 101
    document = Document(doc_id="doc-overflow", text=text)
    chunks = ingest.chunk_document(document, max_chars=100, overlap_chars=0)
    assert len(chunks) == 2


def test_chunk_document_with_overlap_step_and_correct_text() -> None:
    """Chunking com overlap: step = max_chars - overlap_chars."""
    text = "abcde"
    document = Document(doc_id="doc-ov", text=text)
    # max_chars=3, overlap_chars=1 → step=2, starts: 0, 2, 4
    chunks = ingest.chunk_document(document, max_chars=3, overlap_chars=1)
    assert len(chunks) == 3
    assert chunks[0].text == "abc"
    assert chunks[1].text == "cde"
    assert chunks[2].text == "e"


def test_chunk_document_all_whitespace_text_produces_no_chunks() -> None:
    """Texto composto só de espaços após split deve ser rejeitado.

    Nota: Document.__post_init__ rejeita texto whitespace-only antes mesmo de
    chunk_document ser chamado. Este teste verifica que a proteção existe no
    ponto de entrada certo.
    """
    with pytest.raises(ValueError, match="text cannot be empty"):
        Document(doc_id="doc-ws", text="    ")


def test_sparse_vector_index_zero_is_valid() -> None:
    sv = SparseVector(indices=(0,), values=(1.0,))
    assert sv.indices == (0,)


def test_sparse_vector_large_index_is_valid() -> None:
    sv = SparseVector(indices=(2**20,), values=(0.5,))
    assert sv.indices == (2**20,)


def test_sparse_vector_single_element_is_valid() -> None:
    sv = SparseVector(indices=(42,), values=(0.9,))
    assert len(sv.indices) == 1


def test_dense_all_zeros_vector_is_valid() -> None:
    points = ingest.prepare_hybrid_points(
        chunks=[_make_chunk()],
        dense_vectors=[[0.0, 0.0, 0.0]],
        sparse_vectors=[SparseVector(indices=(1,), values=(1.0,))],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=3,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
    )
    assert points[0].dense_vector == (0.0, 0.0, 0.0)


def test_dense_single_dimension_is_valid() -> None:
    points = ingest.prepare_hybrid_points(
        chunks=[_make_chunk()],
        dense_vectors=[[0.5]],
        sparse_vectors=[SparseVector(indices=(1,), values=(1.0,))],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=1,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
    )
    assert len(points[0].dense_vector) == 1


def test_load_corpus_skips_empty_files(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_text("   \n", encoding="utf-8")
    (tmp_path / "valid.txt").write_text("not empty", encoding="utf-8")
    documents = ingest.load_corpus_from_path(tmp_path)
    assert len(documents) == 1
    assert documents[0].source == "valid.txt"


def test_load_corpus_single_file_path(tmp_path: Path) -> None:
    f = tmp_path / "single.txt"
    f.write_text("single file content", encoding="utf-8")
    documents = ingest.load_corpus_from_path(f)
    assert len(documents) == 1
    assert documents[0].text == "single file content"


def test_load_corpus_non_txt_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("markdown content", encoding="utf-8")
    with pytest.raises(ValueError, match=".txt"):
        ingest.load_corpus_from_path(f)


def test_load_corpus_max_documents_limits_results(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"doc{i:02d}.txt").write_text(f"content {i}", encoding="utf-8")
    documents = ingest.load_corpus_from_path(tmp_path, max_documents=3)
    assert len(documents) == 3


def test_load_corpus_max_documents_zero_raises(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match="max_documents must be >= 1"):
        ingest.load_corpus_from_path(tmp_path, max_documents=0)


def test_load_corpus_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ingest.load_corpus_from_path(Path("/definitely/does/not/exist"))


def test_make_chunk_id_different_doc_id_produces_different_id() -> None:
    """doc_id diferente com mesmo texto e índice → chunk_id diferente."""
    id_a = ingest.make_chunk_id("doc-a", 0, "same text")
    id_b = ingest.make_chunk_id("doc-b", 0, "same text")
    assert id_a != id_b


def test_make_chunk_id_different_index_produces_different_id() -> None:
    """chunk_index diferente → chunk_id diferente."""
    id_0 = ingest.make_chunk_id("doc-a", 0, "same text")
    id_1 = ingest.make_chunk_id("doc-a", 1, "same text")
    assert id_0 != id_1


# ===========================================================================
# E. COMPLETUDE DO SUMMARY
# ===========================================================================


def _make_summary(**overrides: object) -> ingest.HybridIngestSummary:
    defaults: dict[str, Any] = {
        "collection_name": HYBRID_COLLECTION_NAME,
        "documents_count": 1,
        "chunks_count": 1,
        "points_prepared": 1,
        "points_sent": 0,
        "batches_sent": 0,
        "dense_ms": 1.0,
        "sparse_ms": 1.0,
        "upload_ms": 0.0,
        "total_ms": 2.0,
        "dry_run": True,
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "embedding_provider": DEFAULT_EMBEDDING_PROVIDER,
        "embedding_dimensions": DEFAULT_EMBEDDING_DIMENSIONS,
        "embedding_version": DEFAULT_EMBEDDING_VERSION,
        "dense_vector_name": DENSE_VECTOR_NAME,
        "sparse_vector_name": SPARSE_VECTOR_NAME,
        "batch_size": DEFAULT_BATCH_SIZE,
    }
    defaults.update(overrides)
    return ingest.HybridIngestSummary(**defaults)


def test_summary_to_safe_dict_has_exactly_18_keys() -> None:
    """to_safe_dict() deve emitir exatamente 18 chaves — nem mais, nem menos."""
    safe = _make_summary().to_safe_dict()
    expected_keys = {
        "collection_name",
        "documents_count",
        "chunks_count",
        "points_prepared",
        "points_sent",
        "batches_sent",
        "dense_ms",
        "sparse_ms",
        "upload_ms",
        "total_ms",
        "dry_run",
        "embedding_model",
        "embedding_provider",
        "embedding_dimensions",
        "embedding_version",
        "dense_vector_name",
        "sparse_vector_name",
        "batch_size",
    }
    assert set(safe.keys()) == expected_keys, (
        f"Unexpected keys: {set(safe.keys()) - expected_keys} | "
        f"Missing keys: {expected_keys - set(safe.keys())}"
    )


def test_summary_rejects_negative_documents_count() -> None:
    with pytest.raises(ValueError, match="documents_count must be non-negative"):
        _make_summary(documents_count=-1)


def test_summary_rejects_negative_chunks_count() -> None:
    with pytest.raises(ValueError, match="chunks_count must be non-negative"):
        _make_summary(chunks_count=-1)


def test_summary_rejects_negative_points_sent() -> None:
    with pytest.raises(ValueError, match="points_sent must be non-negative"):
        _make_summary(points_sent=-1)


def test_summary_rejects_negative_total_ms() -> None:
    with pytest.raises(ValueError, match="total_ms must be non-negative"):
        _make_summary(total_ms=-1.0)


def test_summary_dry_run_flag_true_is_preserved() -> None:
    assert _make_summary(dry_run=True).to_safe_dict()["dry_run"] is True


def test_summary_dry_run_flag_false_is_preserved() -> None:
    assert _make_summary(dry_run=False).to_safe_dict()["dry_run"] is False


def test_summary_json_serialisable() -> None:
    """to_safe_dict() deve ser serializável via json.dumps sem erros."""
    import json

    safe = _make_summary().to_safe_dict()
    json_str = json.dumps(safe)
    assert json_str  # não deve ser vazio


# ===========================================================================
# F. INVARIANTES ESTÁTICOS — análise AST do módulo de produção
# ===========================================================================


def test_script_does_not_use_uuid4() -> None:
    """uuid4() produziria IDs não-determinísticos — proibido."""
    source = _production_source()
    assert "uuid4" not in source, (
        "uuid4 encontrado no script — IDs não seriam determinísticos"
    )


def test_script_does_not_import_random_module() -> None:
    """random quebraria determinismo de IDs."""
    tree = _production_ast()
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])
    assert "random" not in imported_roots


def test_script_does_not_import_known_forbidden_third_party() -> None:
    """Script de produção usa apenas stdlib — sem third-party que vaze ou crie dependência."""
    forbidden: set[str] = {
        "qdrant_client",
        "langchain",
        "sentence_transformers",
        "transformers",
        "torch",
        "fastapi",
        "httpx",
        "requests",
        "openai",
        "anthropic",
        "ollama",
    }
    tree = _production_ast()
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])
    violations = imported_roots & forbidden
    assert not violations, f"Third-party proibido encontrado: {violations}"


def test_script_constants_have_correct_values() -> None:
    """Contrato de valores das constantes públicas."""
    assert ingest.HYBRID_COLLECTION_NAME == "quimera_knowledge_v2"
    assert ingest.LEGACY_COLLECTION_NAME == "quimera_knowledge"
    assert ingest.DENSE_VECTOR_NAME == "dense"
    assert ingest.SPARSE_VECTOR_NAME == "sparse"
    assert ingest.DEFAULT_EMBEDDING_DIMENSIONS == 1024
    assert ingest.DEFAULT_BATCH_SIZE == 32
    assert ingest.MAX_BATCH_SIZE == 256
    assert ingest.SCHEMA_VERSION == "qdrant-hybrid-v2"
    assert LEGACY_COLLECTION_NAME in ingest.PROTECTED_COLLECTIONS
    assert isinstance(ingest.PROTECTED_COLLECTIONS, frozenset)
    assert isinstance(ingest.FORBIDDEN_SUMMARY_KEYS, frozenset)


def test_protected_collections_contains_only_legacy() -> None:
    """PROTECTED_COLLECTIONS deve conter exatamente quimera_knowledge e nada mais.

    Se outra collection for adicionada acidentalmente, algum workflow pode quebrar.
    """
    assert ingest.PROTECTED_COLLECTIONS == frozenset({"quimera_knowledge"})


def test_forbidden_summary_keys_contains_all_expected_keys() -> None:
    """FORBIDDEN_SUMMARY_KEYS deve cobrir todos os tipos de dado sensível."""
    required_forbidden = {
        "text",
        "chunk_text",
        "raw_text",
        "content",
        "page_content",
        "vector",
        "vectors",
        "dense_vector",
        "sparse_vector",
        "embedding",
        "embeddings",
        "prompt",
        "answer",
        "payload",
    }
    assert required_forbidden.issubset(ingest.FORBIDDEN_SUMMARY_KEYS), (
        f"Chaves sensíveis faltando em FORBIDDEN_SUMMARY_KEYS: "
        f"{required_forbidden - ingest.FORBIDDEN_SUMMARY_KEYS}"
    )


def test_make_chunk_id_uses_sha256_not_random_hash() -> None:
    """make_chunk_id deve usar sha256 explicitamente, não hash() nativo do Python.

    hash() é não-determinístico entre processos Python 3.3+ (PYTHONHASHSEED).
    """
    source = _production_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "make_chunk_id":
            function_source = ast.get_source_segment(source, node) or ""
            assert "sha256" in function_source, "make_chunk_id não usa sha256"
            assert "uuid4" not in function_source, "make_chunk_id usa uuid4"
            return
    pytest.fail("make_chunk_id não encontrado no módulo")


# ===========================================================================
# G. UPLOAD EDGE CASES
# ===========================================================================


async def test_upload_dry_run_never_calls_upsert_even_with_100_points() -> None:
    client = FakeUpsertClient()
    points = [_one_point() for _ in range(100)]
    sent, batches, _ = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=points,
        batch_size=DEFAULT_BATCH_SIZE,
        dry_run=True,
        clock=FakeClock(),
    )
    assert sent == 0
    assert batches == 0
    assert client.calls == []


async def test_upload_five_points_two_per_batch_exact_pattern() -> None:
    """5 pontos, batch_size=2 → 3 chamadas [2,2,1], points_sent=5, batches_sent=3."""
    client = FakeUpsertClient()
    points = [_one_point() for _ in range(5)]
    sent, batches, _ = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=points,
        batch_size=2,
        dry_run=False,
        clock=FakeClock(),
    )
    assert sent == 5
    assert batches == 3
    assert [len(call[1]) for call in client.calls] == [2, 2, 1]


async def test_upload_batch_size_one_sends_one_point_per_call() -> None:
    client = FakeUpsertClient()
    points = [_one_point() for _ in range(3)]
    sent, batches, _ = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=points,
        batch_size=1,
        dry_run=False,
        clock=FakeClock(),
    )
    assert sent == 3
    assert batches == 3
    assert all(len(call[1]) == 1 for call in client.calls)


async def test_upload_collection_used_in_all_batch_calls_is_hybrid() -> None:
    """Todas as chamadas ao client devem usar HYBRID_COLLECTION_NAME, nunca outra."""
    client = FakeUpsertClient()
    await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=[_one_point() for _ in range(4)],
        batch_size=2,
        dry_run=False,
        clock=FakeClock(),
    )
    collections_used = {call[0] for call in client.calls}
    assert collections_used == {HYBRID_COLLECTION_NAME}


async def test_upload_failure_wraps_in_hybrid_ingest_error() -> None:
    """Falha do client deve ser encapsulada em HybridIngestError, não propagada raw."""
    client = FakeUpsertClient(exc=RuntimeError("connection refused"))
    with pytest.raises(HybridIngestError):
        await ingest.upload_hybrid_points(
            client=client,
            collection_name=HYBRID_COLLECTION_NAME,
            points=[_one_point()],
            batch_size=1,
            dry_run=False,
            clock=FakeClock(),
        )


async def test_upload_failure_message_does_not_contain_original_error_text() -> None:
    """HybridIngestError não deve vazar a mensagem da exceção original."""
    private_message = "private server connection error detail"
    client = FakeUpsertClient(exc=RuntimeError(private_message))
    with pytest.raises(HybridIngestError) as exc_info:
        await ingest.upload_hybrid_points(
            client=client,
            collection_name=HYBRID_COLLECTION_NAME,
            points=[_one_point()],
            batch_size=1,
            dry_run=False,
            clock=FakeClock(),
        )
    assert private_message not in str(exc_info.value)


# ===========================================================================
# H. ISOLAMENTO EXTRÍNSECO — este arquivo não introduz dependências proibidas
# ===========================================================================


def test_extended_tests_do_not_import_qdrant_client() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "qdrant_client" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "qdrant_client" not in node.module


def test_extended_tests_do_not_require_network_or_docker() -> None:
    """Nenhum import de rede, Docker ou Ollama neste arquivo.

    Usa AST para verificar imports reais, não string search (que causaria
    falsos positivos em docstrings e comentários).
    """
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "docker",
        "ollama",
        "httpx",
        "requests",
        "socket",
        "urllib3",
    }
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])
    violations = imported_roots & forbidden_import_roots
    assert not violations, (
        f"Import proibido encontrado nos testes estendidos: {violations}"
    )
