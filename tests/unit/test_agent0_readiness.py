from __future__ import annotations

import unittest

import httpx

from scripts.check_agent0_readiness import (
    assert_readiness_report_sanitized,
    run_readiness,
)


class Agent0ReadinessTests(unittest.TestCase):
    def test_readiness_no_mutation_and_sanitized_report(self) -> None:
        fake_qdrant = _FakeQdrant()

        report = run_readiness(
            qdrant_client_factory=lambda: fake_qdrant,
            http_get=_fake_http_get,
        )

        self.assertEqual(fake_qdrant.mutations, [])
        self.assertGreaterEqual(report["total_checks"], 8)
        assert_readiness_report_sanitized(report)
        self.assertNotIn("prompt", report)
        self.assertNotIn("payload", report)

    def test_readiness_report_sanitizer_rejects_forbidden_keys(self) -> None:
        with self.assertRaises(ValueError):
            assert_readiness_report_sanitized({"api_key": "sentinel"})


class _FakeQdrant:
    def __init__(self) -> None:
        self.mutations: list[str] = []

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in {"openclaw_internal", "openclaw_financial"}

    def create_collection(self, collection_name: str) -> None:
        self.mutations.append(collection_name)


def _fake_http_get(url: str, **kwargs: object) -> httpx.Response:
    del kwargs
    if url.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "local_chat"}]})
    if url.endswith("/api/tags"):
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:14b"},
                    {"name": "nomic-embed-text"},
                ]
            },
        )
    return httpx.Response(404)


if __name__ == "__main__":
    unittest.main()
