"""Tests for the PR-04A versioned embedding profile contract."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from backend.rag.embedding_config import (
    EmbeddingProfileConfig,
    EmbeddingsConfig,
    load_embeddings_config,
)
from backend.rag.embedding_metadata import (
    compute_profile_fingerprint,
    profiles_are_compatible,
)


def _valid_embeddings_config() -> dict[str, Any]:
    return {
        "embeddings": {
            "config_version": "1.0.0",
            "active_profile": "nomic_dense_v1",
            "candidate_profiles": ["qwen3_dense_8b_v1"],
            "profiles": {
                "nomic_dense_v1": {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                    "model_family": "nomic",
                    "version": "v1",
                    "dimensions": 768,
                    "effective_dimensions": None,
                    "mrl_supported": False,
                    "context_length": 2048,
                    "distance": "cosine",
                    "normalized": True,
                    "instruction_aware": False,
                    "query_instruction": None,
                    "document_instruction": None,
                    "profile_fingerprint": None,
                },
                "qwen3_dense_8b_v1": {
                    "provider": "sentence_transformers",
                    "model": "Qwen/Qwen3-Embedding-8B",
                    "model_family": "qwen3",
                    "version": "v1",
                    "dimensions": 4096,
                    "effective_dimensions": None,
                    "mrl_supported": True,
                    "context_length": 32768,
                    "distance": "cosine",
                    "normalized": True,
                    "instruction_aware": True,
                    "query_instruction": (
                        "Given a financial knowledge retrieval query in Brazilian "
                        "Portuguese or English, retrieve relevant passages that "
                        "answer the query."
                    ),
                    "document_instruction": None,
                    "profile_fingerprint": None,
                },
            },
            "collection_bindings": {
                "openclaw_internal": {"profile": "nomic_dense_v1"},
                "openclaw_financial": {"profile": "nomic_dense_v1"},
            },
        }
    }


def _embeddings_section(data: dict[str, Any]) -> dict[str, Any]:
    embeddings = data["embeddings"]
    if not isinstance(embeddings, dict):
        raise AssertionError("embeddings is not a mapping")
    return cast("dict[str, Any]", embeddings)


def _profiles(data: dict[str, Any]) -> dict[str, Any]:
    profiles = _embeddings_section(data)["profiles"]
    if not isinstance(profiles, dict):
        raise AssertionError("profiles is not a mapping")
    return cast("dict[str, Any]", profiles)


def _profile(data: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profile = _profiles(data)[profile_id]
    if not isinstance(profile, dict):
        raise AssertionError(f"profile {profile_id!r} is not a mapping")
    return cast("dict[str, Any]", profile)


def _collection_bindings(data: dict[str, Any]) -> dict[str, Any]:
    bindings = _embeddings_section(data)["collection_bindings"]
    if not isinstance(bindings, dict):
        raise AssertionError("collection_bindings is not a mapping")
    return cast("dict[str, Any]", bindings)


def _load_config(data: dict[str, Any]) -> EmbeddingsConfig:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "embeddings.yaml"
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return load_embeddings_config(path)


def _load_embeddings_mapping(data: dict[str, Any]) -> EmbeddingsConfig:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "embeddings.yaml"
        path.write_text(
            yaml.safe_dump(
                _embeddings_section(data),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return load_embeddings_config(path)


class EmbeddingConfigTests(unittest.TestCase):
    """Schema and contract tests for embedding profile metadata."""

    def test_valid_nomic_profile(self) -> None:
        config = _load_config(_valid_embeddings_config())

        nomic = config.profiles["nomic_dense_v1"]
        self.assertEqual(config.active_profile, "nomic_dense_v1")
        self.assertEqual(nomic.provider, "ollama")
        self.assertEqual(nomic.model, "nomic-embed-text")
        self.assertEqual(nomic.dimensions, 768)
        self.assertFalse(nomic.instruction_aware)

    def test_valid_qwen3_profile_as_candidate(self) -> None:
        config = _load_config(_valid_embeddings_config())

        qwen3 = config.profiles["qwen3_dense_8b_v1"]
        self.assertIn("qwen3_dense_8b_v1", config.candidate_profiles)
        self.assertEqual(qwen3.model, "Qwen/Qwen3-Embedding-8B")
        self.assertEqual(qwen3.dimensions, 4096)
        self.assertEqual(qwen3.context_length, 32768)
        self.assertTrue(qwen3.mrl_supported)
        self.assertTrue(qwen3.instruction_aware)
        self.assertIsNotNone(qwen3.query_instruction)

    def test_model_family_is_normalized_before_known_dimension_checks(self) -> None:
        data = _valid_embeddings_config()
        _profile(data, "qwen3_dense_8b_v1")["model_family"] = "Qwen3"

        config = _load_config(data)

        self.assertEqual(config.profiles["qwen3_dense_8b_v1"].model_family, "qwen3")

    def test_load_accepts_embeddings_mapping_without_wrapper(self) -> None:
        config = _load_embeddings_mapping(_valid_embeddings_config())

        self.assertEqual(config.config_version, "1.0.0")
        self.assertEqual(config.active_profile, "nomic_dense_v1")

    def test_active_profile_guard_blocks_qwen3(self) -> None:
        data = _valid_embeddings_config()
        _embeddings_section(data)["active_profile"] = "qwen3_dense_8b_v1"

        with self.assertRaisesRegex(
            ValueError,
            "active_profile 'qwen3_dense_8b_v1' is not enabled in RAG-1A",
        ):
            _load_config(data)

    def test_dimensions_required_and_correct(self) -> None:
        missing_dimensions = _valid_embeddings_config()
        del _profile(missing_dimensions, "nomic_dense_v1")["dimensions"]
        with self.assertRaises(ValidationError):
            _load_config(missing_dimensions)

        wrong_nomic = _valid_embeddings_config()
        _profile(wrong_nomic, "nomic_dense_v1")["dimensions"] = 4096
        with self.assertRaisesRegex(ValueError, "dimensions=768"):
            _load_config(wrong_nomic)

        wrong_qwen3 = _valid_embeddings_config()
        _profile(wrong_qwen3, "qwen3_dense_8b_v1")["dimensions"] = 768
        with self.assertRaisesRegex(ValueError, "dimensions=4096"):
            _load_config(wrong_qwen3)

    def test_mrl_inconsistent_effective_dimensions(self) -> None:
        unsupported_mrl = _valid_embeddings_config()
        _profile(unsupported_mrl, "nomic_dense_v1")["effective_dimensions"] = 512
        with self.assertRaisesRegex(ValueError, "mrl_supported=true"):
            _load_config(unsupported_mrl)

        too_large = _valid_embeddings_config()
        _profile(too_large, "qwen3_dense_8b_v1")["effective_dimensions"] = 8192
        with self.assertRaisesRegex(
            ValueError,
            "effective_dimensions must be <= dimensions",
        ):
            _load_config(too_large)

    def test_instruction_aware_contract(self) -> None:
        qwen_without_instruction = _valid_embeddings_config()
        _profile(qwen_without_instruction, "qwen3_dense_8b_v1")[
            "query_instruction"
        ] = None
        with self.assertRaisesRegex(ValueError, "requires query_instruction"):
            _load_config(qwen_without_instruction)

        nomic_with_instruction = _valid_embeddings_config()
        _profile(nomic_with_instruction, "nomic_dense_v1")[
            "query_instruction"
        ] = "Use this query instruction."
        with self.assertRaisesRegex(ValueError, "query_instruction=null"):
            _load_config(nomic_with_instruction)

    def test_distance_normalization_contract(self) -> None:
        invalid_normalized = _valid_embeddings_config()
        _profile(invalid_normalized, "nomic_dense_v1")["distance"] = "euclidean"
        with self.assertRaisesRegex(ValueError, "distance in"):
            _load_config(invalid_normalized)

        invalid_dot = _valid_embeddings_config()
        nomic = _profile(invalid_dot, "nomic_dense_v1")
        nomic["normalized"] = False
        nomic["distance"] = "dot"
        with self.assertRaisesRegex(ValueError, "cannot use distance='dot'"):
            _load_config(invalid_dot)

    def test_context_length_limits(self) -> None:
        nomic_too_long = _valid_embeddings_config()
        _profile(nomic_too_long, "nomic_dense_v1")["context_length"] = 2049
        with self.assertRaisesRegex(ValueError, "context_length <= 2048"):
            _load_config(nomic_too_long)

        qwen_too_long = _valid_embeddings_config()
        _profile(qwen_too_long, "qwen3_dense_8b_v1")["context_length"] = 32769
        with self.assertRaisesRegex(ValueError, "context_length <= 32768"):
            _load_config(qwen_too_long)

    def test_active_profile_exists_and_bindings_resolve(self) -> None:
        missing_active = _valid_embeddings_config()
        _embeddings_section(missing_active)["active_profile"] = "missing_profile"
        with self.assertRaisesRegex(ValueError, "active_profile 'missing_profile'"):
            _load_config(missing_active)

        missing_binding = _valid_embeddings_config()
        _collection_bindings(missing_binding)["openclaw_internal"] = {
            "profile": "missing_profile"
        }
        with self.assertRaisesRegex(ValueError, "collection_bindings"):
            _load_config(missing_binding)

    def test_candidate_profiles_must_exist(self) -> None:
        data = _valid_embeddings_config()
        _embeddings_section(data)["candidate_profiles"] = ["missing_profile"]

        with self.assertRaisesRegex(ValueError, "candidate_profiles"):
            _load_config(data)

    def test_collection_bindings_must_remain_on_active_nomic_in_rag1a(self) -> None:
        data = _valid_embeddings_config()
        _collection_bindings(data)["openclaw_financial"] = {
            "profile": "qwen3_dense_8b_v1"
        }

        with self.assertRaisesRegex(
            ValueError,
            "must remain bound to active_profile 'nomic_dense_v1'",
        ):
            _load_config(data)

    def test_extra_fields_are_forbidden(self) -> None:
        data = _valid_embeddings_config()
        _profile(data, "nomic_dense_v1")["unexpected"] = "blocked"

        with self.assertRaises(ValidationError) as ctx:
            _load_config(data)
        self.assertIn("Extra inputs are not permitted", str(ctx.exception))

    def test_config_version_must_start_with_one(self) -> None:
        data = _valid_embeddings_config()
        _embeddings_section(data)["config_version"] = "2.0.0"

        with self.assertRaisesRegex(ValueError, "config_version"):
            _load_config(data)

    def test_version_format_is_fixed(self) -> None:
        data = _valid_embeddings_config()
        _profile(data, "nomic_dense_v1")["version"] = "1"

        with self.assertRaisesRegex(ValueError, "version must match"):
            _load_config(data)

    def test_profile_fingerprint_is_computed_and_validated_when_declared(self) -> None:
        data = _valid_embeddings_config()
        profile = EmbeddingProfileConfig.model_validate(
            _profile(data, "nomic_dense_v1")
        )
        fingerprint = compute_profile_fingerprint(profile)
        _profile(data, "nomic_dense_v1")["profile_fingerprint"] = fingerprint

        config = _load_config(data)

        self.assertEqual(
            config.profiles["nomic_dense_v1"].profile_fingerprint,
            fingerprint,
        )
        self.assertEqual(len(fingerprint), 16)

    def test_profile_fingerprint_mismatch_is_rejected(self) -> None:
        data = _valid_embeddings_config()
        _profile(data, "nomic_dense_v1")["profile_fingerprint"] = "badfingerprint"

        with self.assertRaisesRegex(ValueError, "profile_fingerprint"):
            _load_config(data)

    def test_profiles_are_compatible_only_for_same_vector_space(self) -> None:
        data = _valid_embeddings_config()
        nomic_a = EmbeddingProfileConfig.model_validate(
            _profile(data, "nomic_dense_v1")
        )
        nomic_b = EmbeddingProfileConfig.model_validate(
            deepcopy(_profile(data, "nomic_dense_v1"))
        )
        qwen3 = EmbeddingProfileConfig.model_validate(
            _profile(data, "qwen3_dense_8b_v1")
        )

        self.assertTrue(profiles_are_compatible(nomic_a, nomic_b))
        self.assertFalse(profiles_are_compatible(nomic_a, qwen3))

    def test_profile_fingerprint_changes_with_vector_space_fields(self) -> None:
        data = _valid_embeddings_config()
        profile_data = deepcopy(_profile(data, "nomic_dense_v1"))
        first = EmbeddingProfileConfig.model_validate(profile_data)
        profile_data["document_instruction"] = "Different document instruction."
        second = EmbeddingProfileConfig.model_validate(profile_data)

        self.assertNotEqual(
            compute_profile_fingerprint(first),
            compute_profile_fingerprint(second),
        )

    def test_loader_rejects_non_mapping_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "embeddings.yaml"
            path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must contain a mapping"):
                load_embeddings_config(path)


if __name__ == "__main__":
    unittest.main()
