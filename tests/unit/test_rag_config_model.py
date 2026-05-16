"""Tests for the RAG-1A PR-04 retrieval config contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from config.rag_config_model import RagConfig, load_rag_config

REPO_ROOT = Path(__file__).parent.parent.parent
PROJECT_RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"


def _valid_config() -> dict[str, Any]:
    return {
        "config_version": "1.0.0",
        "retrieval": {
            "mode": "dense",
            "max_rounds": 1,
            "top_k": 10,
            "fusion": {"strategy": "rrf", "rrf_k": 60},
            "min_score": None,
            "no_result_fallback": "empty",
            "query_rewrite": {
                "enabled": False,
                "model": None,
                "max_attempts": 1,
            },
        },
        "hybrid_search": {
            "enabled": False,
            "dense_vector_name": "dense",
            "sparse_vector_name": "sparse",
            "collections": {
                "internal": "openclaw_internal",
                "financial": "openclaw_financial",
                "default": "openclaw_internal",
            },
            "dense": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dimensions": 768,
                "model_version": "1.0",
            },
            "sparse": {
                "provider": "fastembed",
                "model": "Qdrant/bm25",
                "tokenizer_language": "portuguese",
                "model_version": "1.0",
            },
        },
        "agentic_policy": {
            "enabled": False,
            "allow_query_decomposition": False,
            "allow_iterative_retrieval": False,
            "max_retrieval_steps": 1,
            "max_tool_calls": 1,
            "max_query_rewrites": 0,
            "max_context_reads": 1,
        },
        "tool_metadata": {
            "name": "search_knowledge",
            "description": (
                "Busca os top-k trechos mais relevantes dos corpora do QUIMERA. "
                "Use antes de gerar qualquer resposta que dependa de informação "
                "factual de documentos internos ou ativos financeiros."
            ),
            "parameters": [
                {"name": "query", "type": "string", "required": True},
                {
                    "name": "corpus",
                    "type": "string",
                    "required": False,
                    "enum": ["internal", "financial"],
                    "default": "internal",
                },
                {
                    "name": "top_k",
                    "type": "integer",
                    "required": False,
                    "default": 10,
                },
            ],
        },
    }


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data[name]
    if not isinstance(section, dict):
        raise AssertionError(f"section {name!r} is not a mapping")
    return cast("dict[str, Any]", section)


def _load_config(data: dict[str, Any]) -> RagConfig:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "rag_config.yaml"
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return load_rag_config(path)


def _load_text(raw_yaml: str) -> RagConfig:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "rag_config.yaml"
        path.write_text(raw_yaml, encoding="utf-8")
        return load_rag_config(path)


class RagConfigModelTests(unittest.TestCase):
    """Positive and negative tests for ``load_rag_config``."""

    def test_valid_dense_only_config(self) -> None:
        config = _load_config(_valid_config())

        self.assertEqual(config.config_version, "1.0.0")
        self.assertEqual(config.retrieval.mode, "dense")
        self.assertEqual(config.retrieval.top_k, 10)
        self.assertEqual(config.retrieval.fusion.strategy, "rrf")
        self.assertFalse(config.hybrid_search.enabled)
        self.assertEqual(config.hybrid_search.dense.model, "nomic-embed-text")
        self.assertEqual(
            config.hybrid_search.collections.internal,
            "openclaw_internal",
        )

    def test_retrieval_max_rounds_defaults_to_one(self) -> None:
        data = _valid_config()
        del _section(data, "retrieval")["max_rounds"]

        config = _load_config(data)

        self.assertEqual(config.retrieval.max_rounds, 1)

    def test_project_rag_config_example_loads(self) -> None:
        config = load_rag_config(PROJECT_RAG_CONFIG)

        self.assertEqual(config.retrieval.mode, "dense")
        self.assertFalse(config.hybrid_search.enabled)
        self.assertEqual(config.hybrid_search.dense.dimensions, 768)
        self.assertIsNotNone(config.rag)
        self.assertIsNotNone(config.gateway)
        self.assertIsNotNone(config.agent0)

    def test_project_tool_description_is_actionable_for_function_calling(self) -> None:
        config = load_rag_config(PROJECT_RAG_CONFIG)

        self.assertIn("Busca os top-k trechos", config.tool_metadata.description)
        self.assertIn("Use antes de gerar", config.tool_metadata.description)
        self.assertIn("documentos internos", config.tool_metadata.description)
        self.assertIn("ativos financeiros", config.tool_metadata.description)

    def test_dense_only_contract_preserves_current_runtime_fields(self) -> None:
        config = _load_config(_valid_config())

        self.assertEqual(config.retrieval.top_k, 10)
        self.assertEqual(config.hybrid_search.dense.provider, "ollama")
        self.assertEqual(config.hybrid_search.dense.model, "nomic-embed-text")
        self.assertEqual(config.hybrid_search.dense.dimensions, 768)
        self.assertEqual(
            config.hybrid_search.collections.default,
            "openclaw_internal",
        )

    def test_invalid_config_version(self) -> None:
        data = _valid_config()
        data["config_version"] = "2.0.0"

        with self.assertRaisesRegex(ValueError, "config_version"):
            _load_config(data)

    def test_mode_hybrid_not_allowed(self) -> None:
        data = _valid_config()
        _section(data, "retrieval")["mode"] = "hybrid"

        with self.assertRaisesRegex(
            ValueError,
            "retrieval.mode 'hybrid' requires future RAG sprint",
        ):
            _load_config(data)

    def test_mode_agentic_not_allowed(self) -> None:
        data = _valid_config()
        _section(data, "retrieval")["mode"] = "agentic"

        with self.assertRaisesRegex(
            ValueError,
            "retrieval.mode 'agentic' reserved for Agentic RAG sprint",
        ):
            _load_config(data)

    def test_hybrid_enabled_not_allowed(self) -> None:
        data = _valid_config()
        _section(data, "hybrid_search")["enabled"] = True

        with self.assertRaisesRegex(ValidationError, "hybrid_search.enabled"):
            _load_config(data)

    def test_agentic_policy_enabled_not_allowed(self) -> None:
        data = _valid_config()
        _section(data, "agentic_policy")["enabled"] = True

        with self.assertRaisesRegex(ValidationError, "agentic_policy.enabled"):
            _load_config(data)

    def test_query_rewrite_enabled_not_allowed(self) -> None:
        data = _valid_config()
        retrieval = _section(data, "retrieval")
        _section(retrieval, "query_rewrite")["enabled"] = True

        with self.assertRaisesRegex(ValidationError, "query_rewrite.enabled"):
            _load_config(data)

    def test_invalid_fusion_strategy(self) -> None:
        data = _valid_config()
        retrieval = _section(data, "retrieval")
        _section(retrieval, "fusion")["strategy"] = "dbsf"

        with self.assertRaises(ValidationError) as ctx:
            _load_config(data)
        self.assertIn("fusion.strategy accepts only 'rrf' in RAG-1A PR04", str(ctx.exception))

    def test_invalid_no_result_fallback(self) -> None:
        data = _valid_config()
        _section(data, "retrieval")["no_result_fallback"] = "rewrite_query"

        with self.assertRaisesRegex(ValueError, "no_result_fallback"):
            _load_config(data)

    def test_sparse_tokenizer_language_present(self) -> None:
        config = RagConfig.model_validate(_valid_config())

        self.assertEqual(
            config.hybrid_search.sparse.tokenizer_language,
            "portuguese",
        )

    def test_tool_parameter_type_accepts_function_calling_json_schema_types(self) -> None:
        data = _valid_config()
        tool_metadata = _section(data, "tool_metadata")
        parameters = tool_metadata["parameters"]
        if not isinstance(parameters, list):
            raise AssertionError("tool_metadata.parameters is not a list")
        parameters.extend(
            [
                {"name": "include_metadata", "type": "boolean", "required": False},
                {"name": "filters", "type": "object", "required": False},
                {"name": "tags", "type": "array", "required": False},
            ]
        )

        config = _load_config(data)
        observed_types = {parameter.type for parameter in config.tool_metadata.parameters}

        self.assertTrue({"boolean", "object", "array"}.issubset(observed_types))

    def test_extra_fields_forbidden(self) -> None:
        data = _valid_config()
        _section(data, "retrieval")["unexpected"] = "blocked"

        with self.assertRaises(ValidationError) as ctx:
            _load_config(data)
        self.assertIn("Extra inputs are not permitted", str(ctx.exception))

    def test_extra_fields_forbidden_in_nested_blocks(self) -> None:
        data = _valid_config()
        retrieval = _section(data, "retrieval")
        _section(retrieval, "fusion")["unexpected"] = "blocked"

        with self.assertRaises(ValidationError) as ctx:
            _load_config(data)
        self.assertIn("Extra inputs are not permitted", str(ctx.exception))

    def test_invalid_top_level_field_forbidden(self) -> None:
        data = _valid_config()
        data["runtime_side_effect"] = "blocked"

        with self.assertRaises(ValidationError) as ctx:
            _load_config(data)
        self.assertIn("Extra inputs are not permitted", str(ctx.exception))

    def test_config_requires_yaml_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "YAML mapping"):
            _load_text("- not\n- a\n- mapping\n")


if __name__ == "__main__":
    unittest.main()
