from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, cast

import yaml

from backend.rag.observability import RagEventKind, RagObservabilityEvent
from backend.rag.run_trace import RagRunTrace


REPO_ROOT = Path(__file__).resolve().parents[2]
RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"
CONTRACT_LITELLM_CONFIG = REPO_ROOT / "config" / "litellm_config.yaml"
OPERATIONAL_LITELLM_CONFIG = REPO_ROOT / "infra" / "litellm" / "litellm_config.yaml"
REQUIREMENTS = REPO_ROOT / "infra" / "litellm" / "requirements.txt"
SMOKE_DIR = REPO_ROOT / "tests" / "smoke"

REQUIRED_ALIASES = {
    "local_chat",
    "local_think",
    "local_rag",
    "local_json",
    "quimera_embed",
    "local_embed",
}
CHAT_ALIASES = {"local_chat", "local_think", "local_rag", "local_json"}
EMBED_ALIASES = {"quimera_embed", "local_embed"}
REMOTE_MODEL_PREFIX = re.compile(
    r"^(openai|anthropic|gemini|google|openrouter|xai|azure)/",
    re.IGNORECASE,
)
FORBIDDEN_SERIALIZED_KEYS = {
    "query",
    "question",
    "prompt",
    "answer",
    "response",
    "chunk",
    "chunk_text",
    "chunks",
    "document",
    "documents",
    "vector",
    "vectors",
    "embedding_values",
    "payload",
    "qdrant_payload",
    "portfolio",
    "carteira",
    "api_key",
    "authorization",
    "secret",
    "token",
    "password",
    "headers",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def _aliases(path: Path) -> dict[str, dict[str, Any]]:
    raw = _load_yaml(path)
    model_list = raw["model_list"]
    assert isinstance(model_list, list)
    return {
        str(item["model_name"]): cast(dict[str, Any], item)
        for item in model_list
        if isinstance(item, dict)
    }


class GatewayFinalBaselineTests(unittest.TestCase):
    def test_required_aliases_exist_in_both_litellm_configs(self) -> None:
        for path in (CONTRACT_LITELLM_CONFIG, OPERATIONAL_LITELLM_CONFIG):
            with self.subTest(path=path):
                self.assertEqual(set(_aliases(path)), REQUIRED_ALIASES)

    def test_aliases_point_to_local_ollama_models(self) -> None:
        contract_aliases = _aliases(CONTRACT_LITELLM_CONFIG)
        operational_aliases = _aliases(OPERATIONAL_LITELLM_CONFIG)

        for alias in CHAT_ALIASES:
            contract_model = contract_aliases[alias]["litellm_params"]["model"]
            operational_model = operational_aliases[alias]["litellm_params"]["model"]
            self.assertTrue(str(contract_model).startswith("ollama_chat/"))
            self.assertEqual(operational_model, "os.environ/LITELLM_LOCAL_CHAT_MODEL")
        for alias in EMBED_ALIASES:
            contract_model = contract_aliases[alias]["litellm_params"]["model"]
            operational_model = operational_aliases[alias]["litellm_params"]["model"]
            self.assertEqual(contract_model, "ollama/nomic-embed-text")
            self.assertEqual(operational_model, "os.environ/LITELLM_LOCAL_EMBED_MODEL")

    def test_no_remote_provider_aliases_are_active(self) -> None:
        for path in (CONTRACT_LITELLM_CONFIG, OPERATIONAL_LITELLM_CONFIG):
            aliases = _aliases(path)
            for alias, item in aliases.items():
                with self.subTest(path=path, alias=alias):
                    params = item["litellm_params"]
                    model = str(params["model"])
                    self.assertFalse(REMOTE_MODEL_PREFIX.match(model))
                    self.assertNotIn("api_key", params)
                    self.assertEqual(item["model_info"]["provider"], "ollama")

    def test_rag_config_records_final_gateway_embedding_baseline(self) -> None:
        raw = _load_yaml(RAG_CONFIG)
        rag = raw["rag"]
        embedding = rag["embedding"]

        self.assertIn("tracing", rag)
        self.assertIn("observability", rag)
        self.assertEqual(embedding["active_backend"], "gateway_litellm")
        self.assertEqual(embedding["embedding_backend"], "gateway_litellm_current")
        self.assertEqual(embedding["legacy_embedding_backend"], "direct_ollama")
        self.assertEqual(embedding["embedding_alias"], "quimera_embed")
        self.assertEqual(embedding["gateway_embedding_alias"], "quimera_embed")
        self.assertEqual(embedding["gateway_compatibility_alias"], "local_embed")
        self.assertEqual(embedding["embedding_model"], "nomic-embed-text")
        self.assertEqual(embedding["embedding_dimensions"], 768)
        self.assertTrue(embedding["reindex_required_on_model_change"])

    def test_smoke_tests_remain_guarded_by_explicit_env_vars(self) -> None:
        guards = {
            "RUN_LITELLM_SMOKE": SMOKE_DIR / "test_gateway_runtime_smoke.py",
            "RUN_LITELLM_EMBED_SMOKE": SMOKE_DIR / "test_gateway_embed_smoke.py",
            "RUN_RAG_E2E_SMOKE": SMOKE_DIR / "test_rag_e2e_gateway_smoke.py",
            "RUN_GW08_EMBEDDING_MIGRATION_SMOKE": (
                SMOKE_DIR / "test_rag_gateway_embedding_migration_smoke.py"
            ),
            "RUN_GW08_EMBEDDING_PARITY_SMOKE": (
                SMOKE_DIR / "test_rag_gateway_embedding_migration_smoke.py"
            ),
        }

        for guard, path in guards.items():
            with self.subTest(guard=guard):
                self.assertIn(guard, path.read_text(encoding="utf-8"))

    def test_trace_and_event_serialization_exclude_forbidden_keys(self) -> None:
        trace = RagRunTrace(
            query_id="query-id",
            timestamp_utc="2026-05-01T00:00:00Z",
            collection_name="synthetic_collection",
            embedding_backend="gateway_litellm_current",
            embedding_model="nomic-embed-text",
            embedding_alias="quimera_embed",
            embedding_dimensions=768,
            retrieval_latency_ms=1.0,
            generation_latency_ms=2.0,
            chunk_count=1,
        )
        event = RagObservabilityEvent(
            event_kind=RagEventKind.EMBEDDING_CALL_FINISHED,
            timestamp_utc="2026-05-01T00:00:00Z",
            backend="gateway_litellm",
            alias="quimera_embed",
            dimensions=768,
            latency_ms=1.0,
            batch_size=1,
            status="success",
        )

        for payload in (trace.to_log_dict(), event.to_log_dict()):
            with self.subTest(payload=payload):
                lowered_keys = {key.lower() for key in payload}
                self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint(lowered_keys))

    def test_litellm_requirements_exclude_known_bad_versions(self) -> None:
        text = REQUIREMENTS.read_text(encoding="utf-8")

        self.assertIn("!=1.82.7", text)
        self.assertIn("!=1.82.8", text)
        self.assertNotIn("openai==", text.lower())
        self.assertNotIn("anthropic==", text.lower())


if __name__ == "__main__":
    unittest.main()
