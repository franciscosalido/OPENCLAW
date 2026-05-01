from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from loguru import logger

from backend.rag.observability import (
    RagEventKind,
    RagObservabilityConfig,
    RagObservabilityEvent,
    emit_rag_event,
    load_rag_observability_config,
)


class RagObservabilityConfigTests(unittest.TestCase):
    def test_config_accepts_supported_log_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "info"):
            config = RagObservabilityConfig(log_level=level).validated()
            self.assertIn(config.log_level, {"DEBUG", "INFO", "WARNING"})

    def test_config_rejects_invalid_log_level(self) -> None:
        with self.assertRaises(ValueError):
            RagObservabilityConfig(log_level="TRACE").validated()

    def test_load_config_reads_rag_observability_yaml(self) -> None:
        config_path = Path("tests/tmp_rag_observability_config.yaml")
        config_path.write_text(
            """
rag:
  observability:
    enabled: true
    log_level: "DEBUG"
    embedding_events_enabled: true
    retrieval_events_enabled: false
    generation_events_enabled: true
    collection_guard_events_enabled: false
""",
            encoding="utf-8",
        )
        try:
            config = load_rag_observability_config(config_path)
        finally:
            config_path.unlink()

        self.assertTrue(config.enabled)
        self.assertEqual(config.log_level, "DEBUG")
        self.assertTrue(config.embedding_events_enabled)
        self.assertFalse(config.retrieval_events_enabled)
        self.assertTrue(config.generation_events_enabled)
        self.assertFalse(config.collection_guard_events_enabled)

    def test_emit_rag_event_emits_loguru_bound_event(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            emit_rag_event(
                RagObservabilityEvent(
                    event_kind=RagEventKind.RETRIEVAL_STARTED,
                    timestamp_utc="2026-05-01T00:00:00Z",
                    backend="gateway_litellm_current",
                    alias="quimera_embed",
                    status="started",
                ),
                RagObservabilityConfig(enabled=True, log_level="INFO"),
            )
        finally:
            logger.remove(sink_id)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_kind"], "retrieval_started")
        self.assertEqual(events[0]["status"], "started")

    def test_emit_rag_event_emits_nothing_when_disabled(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            emit_rag_event(
                RagObservabilityEvent(
                    event_kind=RagEventKind.RETRIEVAL_STARTED,
                    timestamp_utc="2026-05-01T00:00:00Z",
                    backend="gateway_litellm_current",
                    alias="quimera_embed",
                    status="started",
                ),
                RagObservabilityConfig(enabled=False),
            )
        finally:
            logger.remove(sink_id)

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
