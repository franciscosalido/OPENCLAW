"""Regression tests for the local LiteLLM operational scripts."""

from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra" / "litellm"
START_SCRIPT = INFRA_DIR / "start_litellm.sh"
CONFIG_PATH = INFRA_DIR / "litellm_config.yaml"
REQUIREMENTS_PATH = INFRA_DIR / "requirements.txt"


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
            REPO_ROOT / "scripts" / "test_opencraw_litellm_runtime.sh",
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


if __name__ == "__main__":
    unittest.main()
