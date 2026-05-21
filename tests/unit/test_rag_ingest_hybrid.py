"""Offline unit tests for PR-09 hybrid ingest script."""

from __future__ import annotations

import ast
import json
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import cast

import pytest

import scripts.rag_ingest_hybrid as ingest
from scripts.rag_ingest_hybrid import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_VERSION,
    DEFAULT_BATCH_SIZE,
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


def doc(doc_id: str = "doc-a", text: str = "abc def ghi", source: str = "unit") -> Document:
    return Document(doc_id=doc_id, text=text, source=source)


def chunk(chunk_id: str = "chunk-a", text: str = "abc") -> Chunk:
    return Chunk(
        doc_id="doc-a",
        chunk_id=chunk_id,
        chunk_index=0,
        text=text,
        source="unit",
    )


def sparse(indices: tuple[int, ...] = (1, 3), values: tuple[float, ...] = (1.0, 0.5)) -> SparseVector:
    return SparseVector(indices=indices, values=values)


def dense(dimensions: int = 3) -> list[float]:
    return [0.1] * dimensions


def prepare_one_point() -> HybridIngestPoint:
    return ingest.prepare_hybrid_points(
        chunks=[chunk()],
        dense_vectors=[dense()],
        sparse_vectors=[sparse()],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=3,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
    )[0]


def test_make_chunk_id_is_deterministic() -> None:
    first = ingest.make_chunk_id("doc-a", 0, "same text")
    second = ingest.make_chunk_id("doc-a", 0, "same text")
    assert first == second


def test_make_chunk_id_changes_when_text_changes() -> None:
    first = ingest.make_chunk_id("doc-a", 0, "first text")
    second = ingest.make_chunk_id("doc-a", 0, "second text")
    assert first != second


def test_make_chunk_id_strips_doc_id_before_hashing() -> None:
    assert ingest.make_chunk_id("doc-a ", 0, "t") == ingest.make_chunk_id("doc-a", 0, "t")


def test_document_rejects_whitespace_only_fields() -> None:
    with pytest.raises(ValueError, match="text cannot be empty"):
        Document(doc_id="doc-a", text="   ")
    with pytest.raises(ValueError, match="doc_id cannot be empty"):
        Document(doc_id="   ", text="safe")


def test_chunk_document_is_deterministic() -> None:
    document = doc(text="abcdefghij")
    first = ingest.chunk_document(document, max_chars=4, overlap_chars=1)
    second = ingest.chunk_document(document, max_chars=4, overlap_chars=1)
    assert first == second
    assert [item.chunk_index for item in first] == [0, 1, 2, 3]


def test_chunk_document_rejects_invalid_sizes() -> None:
    document = doc()
    with pytest.raises(ValueError, match="max_chars"):
        ingest.chunk_document(document, max_chars=0)
    with pytest.raises(ValueError, match="overlap_chars"):
        ingest.chunk_document(document, max_chars=10, overlap_chars=-1)
    with pytest.raises(ValueError, match="overlap_chars must be < max_chars"):
        ingest.chunk_document(document, max_chars=10, overlap_chars=10)


def test_generate_synthetic_corpus_returns_safe_documents() -> None:
    documents = ingest.generate_synthetic_corpus()
    assert len(documents) >= 2
    assert all(document.source == "synthetic" for document in documents)
    assert all("\x00" not in document.text for document in documents)


def test_prepare_hybrid_points_builds_named_vectors_and_payload() -> None:
    point = prepare_one_point()
    vectors = point.to_qdrant_vector_dict()
    assert set(vectors) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}
    assert vectors[DENSE_VECTOR_NAME] == [0.1, 0.1, 0.1]
    assert vectors[SPARSE_VECTOR_NAME] == {"indices": [1, 3], "values": [1.0, 0.5]}
    assert point.payload["doc_id"] == "doc-a"
    assert point.payload["embedding_model"] == DEFAULT_EMBEDDING_MODEL
    assert point.payload["schema_version"] == "qdrant-hybrid-v2"


def test_prepare_hybrid_points_payload_has_exact_expected_keys() -> None:
    point = prepare_one_point()
    assert set(point.payload) == {
        "doc_id",
        "chunk_id",
        "chunk_index",
        "source",
        "embedding_model",
        "embedding_provider",
        "embedding_dimensions",
        "embedding_version",
        "dense_vector_name",
        "sparse_vector_name",
        "schema_version",
    }


def test_prepare_hybrid_points_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        ingest.prepare_hybrid_points(
            chunks=[chunk()],
            dense_vectors=[],
            sparse_vectors=[sparse()],
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=3,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
        )


def test_prepare_hybrid_points_rejects_dense_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="dense vector has"):
        ingest.prepare_hybrid_points(
            chunks=[chunk()],
            dense_vectors=[[0.1, 0.2]],
            sparse_vectors=[sparse()],
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=3,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_prepare_hybrid_points_rejects_non_finite_dense_values(bad_value: float) -> None:
    with pytest.raises(ValueError, match="dense value must be finite"):
        ingest.prepare_hybrid_points(
            chunks=[chunk()],
            dense_vectors=[[0.1, bad_value, 0.3]],
            sparse_vectors=[sparse()],
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=3,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
        )


@pytest.mark.parametrize("bad_value", [True, False])
def test_prepare_hybrid_points_rejects_bool_dense_values(bad_value: bool) -> None:
    with pytest.raises(TypeError, match="dense value must be numeric"):
        ingest.prepare_hybrid_points(
            chunks=[chunk()],
            dense_vectors=[[0.1, bad_value, 0.3]],
            sparse_vectors=[sparse()],
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=3,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
        )


def test_prepare_hybrid_points_rejects_sparse_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        SparseVector(indices=(1,), values=())


def test_sparse_vector_rejects_bool_index() -> None:
    with pytest.raises(TypeError, match="sparse index must be an integer"):
        SparseVector(indices=(True,), values=(1.0,))


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_sparse_vector_rejects_non_finite_values(bad_value: float) -> None:
    with pytest.raises(ValueError, match="sparse value must be finite"):
        SparseVector(indices=(1,), values=(bad_value,))


def test_prepare_hybrid_points_rejects_empty_sparse_by_default() -> None:
    with pytest.raises(ValueError, match="sparse vector cannot be empty"):
        ingest.prepare_hybrid_points(
            chunks=[chunk()],
            dense_vectors=[dense()],
            sparse_vectors=[SparseVector(indices=(), values=())],
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=3,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
        )


def test_prepare_hybrid_points_allows_empty_sparse_when_explicit() -> None:
    points = ingest.prepare_hybrid_points(
        chunks=[chunk()],
        dense_vectors=[dense()],
        sparse_vectors=[SparseVector(indices=(), values=())],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=3,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
        allow_empty_sparse=True,
    )
    assert points[0].sparse_indices == ()
    assert points[0].sparse_values == ()


def test_prepare_hybrid_points_payload_excludes_text_and_vectors() -> None:
    point = prepare_one_point()
    forbidden = {"text", "chunk_text", "dense_vector", "sparse_vector", "embedding", "prompt", "answer"}
    assert forbidden.isdisjoint(point.payload)


def test_hybrid_ingest_point_payload_is_immutable() -> None:
    point = prepare_one_point()
    with pytest.raises(TypeError):
        cast(MutableMapping[str, object], point.payload)["doc_id"] = "mutated"


def test_validate_embedding_metadata_rejects_equal_vector_names() -> None:
    with pytest.raises(ValueError, match="must differ"):
        ingest.validate_embedding_metadata(
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            embedding_version=DEFAULT_EMBEDDING_VERSION,
            dense_vector_name="same",
            sparse_vector_name="same",
        )


def test_assert_collection_rejects_legacy_collection() -> None:
    with pytest.raises(HybridIngestError, match="protected"):
        ingest.assert_collection_is_safe_for_ingest(LEGACY_COLLECTION_NAME)


def test_assert_collection_allows_hybrid_collection() -> None:
    assert ingest.assert_collection_is_safe_for_ingest(HYBRID_COLLECTION_NAME) == HYBRID_COLLECTION_NAME


def test_batched_splits_points_deterministically() -> None:
    items = [1, 2, 3, 4, 5]
    assert list(ingest.batched(items, 2)) == [[1, 2], [3, 4], [5]]


def test_batched_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        list(ingest.batched([1], 0))
    with pytest.raises(ValueError, match=f"<= {MAX_BATCH_SIZE}"):
        list(ingest.batched([1], MAX_BATCH_SIZE + 1))


async def test_upload_dry_run_does_not_call_client() -> None:
    client = FakeUpsertClient()
    sent, batches, _upload_ms = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=[prepare_one_point()],
        batch_size=DEFAULT_BATCH_SIZE,
        dry_run=True,
        clock=FakeClock(),
    )
    assert (sent, batches) == (0, 0)
    assert client.calls == []


async def test_upload_execute_calls_client_in_batches() -> None:
    client = FakeUpsertClient()
    points = [prepare_one_point(), prepare_one_point(), prepare_one_point()]
    sent, batches, _upload_ms = await ingest.upload_hybrid_points(
        client=client,
        collection_name=HYBRID_COLLECTION_NAME,
        points=points,
        batch_size=2,
        dry_run=False,
        clock=FakeClock(),
    )
    assert (sent, batches) == (3, 2)
    assert [len(call[1]) for call in client.calls] == [2, 1]
    assert {call[0] for call in client.calls} == {HYBRID_COLLECTION_NAME}


async def test_upload_never_allows_legacy_collection() -> None:
    with pytest.raises(HybridIngestError, match="protected"):
        await ingest.upload_hybrid_points(
            client=FakeUpsertClient(),
            collection_name=LEGACY_COLLECTION_NAME,
            points=[],
            batch_size=DEFAULT_BATCH_SIZE,
            dry_run=True,
            clock=FakeClock(),
        )


async def test_run_ingest_empty_corpus_returns_zero_summary() -> None:
    dense_embedder = FakeDenseEmbedder()
    sparse_embedder = FakeSparseEmbedder()
    client = FakeUpsertClient()
    summary = await ingest.run_ingest(
        documents=[],
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        upsert_client=client,
        clock=FakeClock(),
    )
    assert summary.documents_count == 0
    assert summary.chunks_count == 0
    assert summary.points_prepared == 0
    assert summary.points_sent == 0
    assert dense_embedder.calls == []
    assert sparse_embedder.calls == []
    assert client.calls == []


async def test_run_ingest_dry_run_prepares_points_but_sends_zero() -> None:
    client = FakeUpsertClient()
    summary = await ingest.run_ingest(
        documents=[doc(text="abc")],
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=client,
        dry_run=True,
        clock=FakeClock(),
    )
    assert summary.points_prepared == 1
    assert summary.points_sent == 0
    assert summary.dry_run is True
    assert client.calls == []


async def test_run_ingest_execute_sends_points_to_hybrid_collection() -> None:
    client = FakeUpsertClient()
    summary = await ingest.run_ingest(
        documents=[doc(text="abc")],
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=client,
        dry_run=False,
        batch_size=1,
        clock=FakeClock(),
    )
    assert summary.points_sent == 1
    assert summary.batches_sent == 1
    assert client.calls[0][0] == HYBRID_COLLECTION_NAME


async def test_run_ingest_applies_max_chunks() -> None:
    summary = await ingest.run_ingest(
        documents=[doc(text="abcdefghij" * 300)],
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=FakeUpsertClient(),
        dry_run=True,
        max_chunks=1,
        clock=FakeClock(),
    )
    assert summary.chunks_count == 1
    assert summary.points_prepared == 1


async def test_run_ingest_rejects_max_chunks_zero() -> None:
    with pytest.raises(ValueError, match="max_chunks must be >= 1"):
        await ingest.run_ingest(
            documents=[doc(text="abcdefghij" * 300)],
            dense_embedder=FakeDenseEmbedder(),
            sparse_embedder=FakeSparseEmbedder(),
            upsert_client=FakeUpsertClient(),
            dry_run=True,
            max_chunks=0,
            clock=FakeClock(),
        )


async def test_run_ingest_is_deterministic_for_same_input() -> None:
    first_client = FakeUpsertClient()
    second_client = FakeUpsertClient()
    document = doc(text="abcdefghij" * 300)
    first = await ingest.run_ingest(
        documents=[document],
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=first_client,
        dry_run=False,
        max_chunks=2,
        batch_size=2,
        clock=FakeClock(),
    )
    second = await ingest.run_ingest(
        documents=[document],
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        upsert_client=second_client,
        dry_run=False,
        max_chunks=2,
        batch_size=2,
        clock=FakeClock(),
    )
    first_ids = [point.point_id for _collection, batch in first_client.calls for point in batch]
    second_ids = [point.point_id for _collection, batch in second_client.calls for point in batch]
    assert first.points_prepared == second.points_prepared == 2
    assert first_ids == second_ids


def test_elapsed_ms_clamps_retrograde_clock_to_zero() -> None:
    assert ingest._elapsed_ms(2.0, 1.0) == 0.0


def test_summary_to_safe_dict_has_no_text_vectors_payload() -> None:
    summary = ingest.HybridIngestSummary(
        collection_name=HYBRID_COLLECTION_NAME,
        documents_count=1,
        chunks_count=1,
        points_prepared=1,
        points_sent=0,
        batches_sent=0,
        dense_ms=1.0,
        sparse_ms=1.0,
        upload_ms=0.0,
        total_ms=2.0,
        dry_run=True,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
        dense_vector_name=DENSE_VECTOR_NAME,
        sparse_vector_name=SPARSE_VECTOR_NAME,
        batch_size=DEFAULT_BATCH_SIZE,
    )
    safe = summary.to_safe_dict()
    assert ingest.FORBIDDEN_SUMMARY_KEYS.isdisjoint(safe)


def test_main_dry_run_outputs_safe_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--synthetic"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["collection_name"] == HYBRID_COLLECTION_NAME
    assert payload["dry_run"] is True
    assert ingest.FORBIDDEN_SUMMARY_KEYS.isdisjoint(payload)


def test_main_rejects_legacy_collection(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--synthetic", "--collection", LEGACY_COLLECTION_NAME])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err
    assert LEGACY_COLLECTION_NAME not in captured.out
    assert LEGACY_COLLECTION_NAME not in captured.err


def test_main_execute_is_blocked_in_pr09(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--synthetic", "--execute"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_nonexistent_corpus_path_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--corpus-path", "/definitely/not/here.txt"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_invalid_batch_size_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--synthetic", "--batch-size", "0"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


def test_main_invalid_max_documents_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ingest.main(["--synthetic", "--max-documents", "0"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hybrid ingest failed" in captured.err


async def test_deterministic_cli_embedders_emit_valid_vectors() -> None:
    dense_vector = await ingest._DeterministicDenseEmbedder().embed("safe text")
    sparse_vector = await ingest._DeterministicSparseEmbedder().embed("safe text")
    assert len(dense_vector) == DEFAULT_EMBEDDING_DIMENSIONS
    assert all(isinstance(value, float) for value in dense_vector)
    assert sparse_vector.indices
    assert len(sparse_vector.indices) == len(sparse_vector.values)
    assert len(set(sparse_vector.indices)) == len(sparse_vector.indices)


def test_all_exports_are_importable() -> None:
    for name in ingest.__all__:
        assert hasattr(ingest, name), name


def test_unit_tests_do_not_import_qdrant_client() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = _imported_roots(tree)
    assert "qdrant_client" not in imported_roots


def test_script_pure_functions_do_not_call_create_or_delete_collection() -> None:
    source = Path(ingest.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"create_collection", "delete_collection"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls


async def test_embedding_failure_is_sanitized() -> None:
    with pytest.raises(HybridIngestError) as exc_info:
        await ingest.run_ingest(
            documents=[doc(text="private chunk text")],
            dense_embedder=FakeDenseEmbedder(exc=RuntimeError("private chunk text")),
            sparse_embedder=FakeSparseEmbedder(),
            upsert_client=FakeUpsertClient(),
            clock=FakeClock(),
        )
    assert "private chunk text" not in str(exc_info.value)


async def test_upsert_failure_is_sanitized() -> None:
    with pytest.raises(HybridIngestError) as exc_info:
        await ingest.run_ingest(
            documents=[doc(text="private chunk text")],
            dense_embedder=FakeDenseEmbedder(),
            sparse_embedder=FakeSparseEmbedder(),
            upsert_client=FakeUpsertClient(exc=RuntimeError("private payload")),
            dry_run=False,
            clock=FakeClock(),
        )
    assert "private payload" not in str(exc_info.value)


def test_no_qdrant_docker_ollama_required() -> None:
    source = Path(ingest.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = _imported_roots(tree)
    assert "qdrant_client" not in imported_roots
    assert "docker" not in imported_roots
    assert "ollama" not in imported_roots


def test_load_corpus_from_path_reads_txt_deterministically(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("second", encoding="utf-8")
    (tmp_path / "a.txt").write_text("first", encoding="utf-8")
    documents = ingest.load_corpus_from_path(tmp_path)
    assert [document.source for document in documents] == ["a.txt", "b.txt"]


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots
