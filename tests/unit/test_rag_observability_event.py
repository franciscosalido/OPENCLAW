from __future__ import annotations

import dataclasses
import unittest

from backend.rag.observability import (
    FORBIDDEN_OBSERVABILITY_KEYS,
    RagErrorCategory,
    RagEventKind,
    RagObservabilityEvent,
)


def _event(**overrides: object) -> RagObservabilityEvent:
    values: dict[str, object] = {
        "event_kind": RagEventKind.EMBEDDING_CALL_STARTED,
        "timestamp_utc": "2026-05-01T00:00:00Z",
        "backend": "gateway_litellm",
        "alias": "quimera_embed",
    }
    values.update(overrides)
    return RagObservabilityEvent(**values)  # type: ignore[arg-type]


class RagObservabilityEventTests(unittest.TestCase):
    def test_event_dataclass_is_frozen(self) -> None:
        event = _event()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.alias = "other"  # type: ignore[misc]

    def test_to_log_dict_uses_allowlist_and_converts_enums(self) -> None:
        data = _event(
            event_kind=RagEventKind.EMBEDDING_CALL_FAILED,
            error_category=RagErrorCategory.TIMEOUT,
            latency_ms=12.5,
            batch_size=2,
            status="failed",
        ).to_log_dict()

        self.assertEqual(data["event_kind"], "embedding_call_failed")
        self.assertEqual(data["error_category"], "timeout")
        self.assertEqual(data["latency_ms"], 12.5)
        self.assertEqual(data["batch_size"], 2)

    def test_to_log_dict_excludes_none_values(self) -> None:
        data = _event().to_log_dict()

        self.assertNotIn("latency_ms", data)
        self.assertNotIn("error_category", data)
        self.assertNotIn("collection_name", data)

    def test_forbidden_content_keys_are_absent(self) -> None:
        data = _event(
            model="nomic-embed-text",
            dimensions=768,
            collection_name="synthetic_collection",
        ).to_log_dict()

        lowered_keys = {key.lower() for key in data}

        self.assertTrue(FORBIDDEN_OBSERVABILITY_KEYS.isdisjoint(lowered_keys))

    def test_negative_latency_raises(self) -> None:
        with self.assertRaises(ValueError):
            _event(latency_ms=-0.1)

    def test_negative_chunk_count_raises(self) -> None:
        with self.assertRaises(ValueError):
            _event(chunk_count=-1)

    def test_invalid_batch_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            _event(batch_size=0)

    def test_invalid_dimensions_raises(self) -> None:
        with self.assertRaises(ValueError):
            _event(dimensions=0)


if __name__ == "__main__":
    unittest.main()
