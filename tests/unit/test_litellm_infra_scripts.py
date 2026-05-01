"""Regression tests for the local LiteLLM operational scripts."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra" / "litellm"
START_SCRIPT = INFRA_DIR / "start_litellm.sh"
HEALTHCHECK_SCRIPT = INFRA_DIR / "healthcheck.sh"
CONFIG_PATH = INFRA_DIR / "litellm_config.yaml"
REQUIREMENTS_PATH = INFRA_DIR / "requirements.txt"

# Pattern matching healthcheck.sh's comment-stripping and remote-marker checks.
_COMMENT_LINE = re.compile(r"^\s*#")
_REMOTE_API_KEY = re.compile(
    r"OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY"
    r"|OPENROUTER_API_KEY|XAI_API_KEY|AZURE_API_KEY",
    re.IGNORECASE,
)
_REMOTE_MODEL_PREFIX = re.compile(
    r"model:\s*(openai|anthropic|gemini|google|openrouter|xai|azure)/",
    re.IGNORECASE,
)


def _strip_yaml_comments(text: str) -> str:
    """Mirror the sed '/^[[:space:]]*#/d' used in healthcheck.sh."""
    return "\n".join(
        line for line in text.splitlines()
        if not _COMMENT_LINE.match(line)
    )


def _has_remote_marker(active_text: str) -> bool:
    """Return True if active (comment-stripped) YAML text contains remote provider markers."""
    return bool(
        _REMOTE_API_KEY.search(active_text)
        or _REMOTE_MODEL_PREFIX.search(active_text)
    )


def _run_start(env_updates: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key, value in env_updates.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class LiteLLMInfraScriptTests(unittest.TestCase):
    def test_shell_scripts_are_executable(self) -> None:
        for path in (
            START_SCRIPT,
            INFRA_DIR / "healthcheck.sh",
            INFRA_DIR / "test_models.sh",
            INFRA_DIR / "test_local_chat.sh",
            REPO_ROOT / "scripts" / "check_litellm_gateway.sh",
            REPO_ROOT / "scripts" / "check_gateway_readiness.sh",
            REPO_ROOT / "scripts" / "test_opencraw_litellm_runtime.sh",
            REPO_ROOT / "scripts" / "test_gw08_embedding_migration.sh",
        ):
            with self.subTest(path=path):
                mode = path.stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, f"{path} is not executable")

    def test_start_refuses_missing_master_key(self) -> None:
        result = _run_start({"LITELLM_MASTER_KEY": None})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LITELLM_MASTER_KEY is required", result.stderr)

    def test_start_refuses_zero_zero_zero_zero(self) -> None:
        result = _run_start(
            {
                "LITELLM_MASTER_KEY": "dev-local-key-change-me",
                "LITELLM_HOST": "0.0.0.0",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to bind LiteLLM", result.stderr)

    def test_start_refuses_remote_ollama_api_base(self) -> None:
        result = _run_start(
            {
                "LITELLM_MASTER_KEY": "dev-local-key-change-me",
                "OLLAMA_API_BASE": "https://api.openai.com",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OLLAMA_API_BASE must be local-only", result.stderr)

    def test_start_refuses_remote_model_override(self) -> None:
        result = _run_start(
            {
                "LITELLM_MASTER_KEY": "dev-local-key-change-me",
                "LITELLM_LOCAL_CHAT_MODEL": "openai/gpt-5",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must use the local Ollama provider", result.stderr)

    def test_operational_config_defines_only_local_aliases(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        model_list = raw["model_list"]
        aliases = {item["model_name"] for item in model_list}

        self.assertEqual(
            aliases,
            {
                "local_chat",
                "local_think",
                "local_rag",
                "local_json",
                "quimera_embed",
                "local_embed",
            },
        )
        for item in model_list:
            params = item["litellm_params"]
            self.assertIn(params["api_base"], {"os.environ/OLLAMA_API_BASE"})
            self.assertNotIn("api_key", params)
            self.assertNotIn("openai", str(params).lower())
            self.assertNotIn("anthropic", str(params).lower())
            self.assertNotIn("gemini", str(params).lower())

    def test_requirements_exclude_compromised_litellm_versions(self) -> None:
        text = REQUIREMENTS_PATH.read_text(encoding="utf-8")

        self.assertIn("!=1.82.7", text)
        self.assertIn("!=1.82.8", text)


class HealthcheckConfigGuardTests(unittest.TestCase):
    """Verify that healthcheck.sh config scanning correctly ignores comments
    and rejects only active remote provider markers."""

    def test_operational_config_passes_comment_stripped_check(self) -> None:
        """infra/litellm/litellm_config.yaml must be clean after comment stripping.

        This is a regression test for the false positive that was caused by
        full-line YAML comments mentioning OpenAI/Anthropic/Gemini being picked
        up by the old broad grep pattern.
        """
        text = CONFIG_PATH.read_text(encoding="utf-8")
        active = _strip_yaml_comments(text)

        self.assertFalse(
            _has_remote_marker(active),
            "Active (non-comment) config content must not contain remote provider markers.",
        )

    def test_config_comments_contain_provider_names_but_active_content_does_not(self) -> None:
        """Documents the root cause: comments mention OpenAI/Anthropic but active lines do not."""
        text = CONFIG_PATH.read_text(encoding="utf-8")
        comment_lines = [l for l in text.splitlines() if _COMMENT_LINE.match(l)]
        has_provider_in_comment = any(
            word in line.lower()
            for line in comment_lines
            for word in ("openai", "anthropic", "gemini")
        )
        self.assertTrue(
            has_provider_in_comment,
            "Expected a YAML comment mentioning a remote provider (documents the false-positive source).",
        )
        active = _strip_yaml_comments(text)
        self.assertFalse(_has_remote_marker(active))

    def test_master_key_env_ref_does_not_trigger_remote_api_key_check(self) -> None:
        """LITELLM_MASTER_KEY must not be treated as a remote provider API key."""
        yaml_snippet = (
            "general_settings:\n"
            "  master_key: os.environ/LITELLM_MASTER_KEY\n"
            "  disable_spend_logs: true\n"
        )
        self.assertFalse(_has_remote_marker(yaml_snippet))

    def test_quimera_embed_and_local_embed_pass_check(self) -> None:
        """Local embedding aliases must not be rejected."""
        yaml_snippet = (
            "- model_name: quimera_embed\n"
            "  litellm_params:\n"
            "    model: os.environ/LITELLM_LOCAL_EMBED_MODEL\n"
            "    api_base: os.environ/OLLAMA_API_BASE\n"
            "- model_name: local_embed\n"
            "  litellm_params:\n"
            "    model: os.environ/LITELLM_LOCAL_EMBED_MODEL\n"
            "    api_base: os.environ/OLLAMA_API_BASE\n"
        )
        self.assertFalse(_has_remote_marker(yaml_snippet))

    def test_active_openai_model_triggers_remote_check(self) -> None:
        """An active model: openai/gpt-4 line must be detected."""
        yaml_snippet = (
            "- model_name: bad_alias\n"
            "  litellm_params:\n"
            "    model: openai/gpt-4\n"
            "    api_base: https://api.openai.com/v1\n"
        )
        self.assertTrue(_has_remote_marker(yaml_snippet))

    def test_active_anthropic_model_triggers_remote_check(self) -> None:
        yaml_snippet = (
            "- model_name: bad_alias\n"
            "  litellm_params:\n"
            "    model: anthropic/claude-3-opus\n"
        )
        self.assertTrue(_has_remote_marker(yaml_snippet))

    def test_active_openai_api_key_env_var_triggers_remote_check(self) -> None:
        yaml_snippet = (
            "- model_name: bad_alias\n"
            "  litellm_params:\n"
            "    model: openai/gpt-4\n"
            "    api_key: os.environ/OPENAI_API_KEY\n"
        )
        self.assertTrue(_has_remote_marker(yaml_snippet))

    def test_commented_out_remote_provider_does_not_trigger_check(self) -> None:
        """A commented-out remote provider block must not be flagged."""
        yaml_snippet = (
            "# - model_name: future_remote\n"
            "#   litellm_params:\n"
            "#     model: openai/gpt-4\n"
            "#     api_key: os.environ/OPENAI_API_KEY\n"
            "- model_name: local_chat\n"
            "  litellm_params:\n"
            "    model: os.environ/LITELLM_LOCAL_CHAT_MODEL\n"
            "    api_base: os.environ/OLLAMA_API_BASE\n"
        )
        active = _strip_yaml_comments(yaml_snippet)
        self.assertFalse(_has_remote_marker(active))

    def test_healthcheck_script_exits_nonzero_on_missing_master_key(self) -> None:
        """healthcheck.sh must fail before config scanning when LITELLM_MASTER_KEY is absent."""
        env = {k: v for k, v in os.environ.items() if k != "LITELLM_MASTER_KEY"}
        result = subprocess.run(
            [str(HEALTHCHECK_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LITELLM_MASTER_KEY is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
