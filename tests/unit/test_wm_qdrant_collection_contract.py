from __future__ import annotations

from backend.working_memory.config import WorkingMemorySettings
from backend.working_memory.qdrant_store import (
    WORKING_MEMORY_PAYLOAD_INDEXES,
    WorkingMemoryQdrantStore,
    qdrant_distance,
)


class FakeCollectionClient:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.indexes: list[tuple[str, object]] = []

    async def collection_exists(self, **kwargs: object) -> bool:
        return False

    async def create_collection(self, **kwargs: object) -> None:
        self.created.append(kwargs)

    async def create_payload_index(self, **kwargs: object) -> None:
        self.indexes.append((str(kwargs["field_name"]), kwargs["field_schema"]))

    async def get_collection(self, **kwargs: object) -> object:
        return {}

    async def upsert(self, **kwargs: object) -> None:
        return None

    async def query_points(self, **kwargs: object) -> object:
        return object()

    async def scroll(self, **kwargs: object) -> tuple[list[object], None]:
        return [], None

    async def set_payload(self, **kwargs: object) -> None:
        return None

    async def delete(self, **kwargs: object) -> None:
        return None


async def test_collection_config_uses_named_in_memory_cosine_vector() -> None:
    settings = WorkingMemorySettings(vector_size=4, collection_name="quimera_working_memory_test_contract")
    client = FakeCollectionClient()
    store = WorkingMemoryQdrantStore(client, settings)

    await store.ensure_collection()

    created = client.created[0]
    vectors = created["vectors_config"]
    assert settings.vector_name in vectors  # type: ignore[operator]
    vector_params = vectors[settings.vector_name]  # type: ignore[index]
    assert vector_params.size == 4
    assert vector_params.distance == qdrant_distance("Cosine")
    assert vector_params.on_disk is False
    assert {name for name, _ in client.indexes} == set(WORKING_MEMORY_PAYLOAD_INDEXES)


def test_collection_contract_does_not_reference_other_quimera_collections() -> None:
    assert "quimera_knowledge" not in WorkingMemoryQdrantStore.__module__
    forbidden = {"quimera_knowledge", "quimera_query_cache", "quimera_llm_cache"}
    assert forbidden.isdisjoint(WORKING_MEMORY_PAYLOAD_INDEXES)


def test_working_memory_store_has_no_delete_collection_method() -> None:
    assert not hasattr(WorkingMemoryQdrantStore, "delete_collection")
