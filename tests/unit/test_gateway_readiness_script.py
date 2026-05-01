from __future__ import annotations

import os
import re
import stat
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_gateway_readiness.sh"


def _run_script(env_updates: dict[str, str | None] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key, value in (env_updates or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class GatewayReadinessScriptTests(unittest.TestCase):
    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_script_uses_strict_shell_mode(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("set -euo pipefail", text)

    def test_default_mode_does_not_require_live_services(self) -> None:
        result = _run_script(
            {
                "QUIMERA_LLM_BASE_URL": None,
                "OLLAMA_API_BASE": None,
                "QDRANT_URL": None,
                "LITELLM_MASTER_KEY": None,
                "QUIMERA_LLM_API_KEY": None,
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Gateway-0 static readiness checks passed", result.stdout)
        self.assertNotIn("/api/tags", result.stdout)
        self.assertNotIn("/healthz", result.stdout)

    def test_refuses_remote_quimera_llm_base_url(self) -> None:
        result = _run_script({"QUIMERA_LLM_BASE_URL": "https://api.example.com/v1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("QUIMERA_LLM_BASE_URL must be local-only", result.stderr)

    def test_refuses_remote_ollama_api_base(self) -> None:
        result = _run_script({"OLLAMA_API_BASE": "https://ollama.example.com"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OLLAMA_API_BASE must be local-only", result.stderr)

    def test_refuses_remote_qdrant_url(self) -> None:
        result = _run_script({"QDRANT_URL": "https://qdrant.example.com"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("QDRANT_URL must be local-only", result.stderr)

    def test_script_checks_required_aliases_and_quimera_embed(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        for alias in (
            "local_chat",
            "local_think",
            "local_rag",
            "local_json",
            "quimera_embed",
            "local_embed",
        ):
            with self.subTest(alias=alias):
                self.assertIn(alias, text)

    def test_script_has_live_opt_in(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--live", text)
        self.assertIn('MODE="static"', text)

    def test_script_does_not_print_secrets(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertNotRegex(text, re.compile(r"echo .*KEY", re.IGNORECASE))
        self.assertNotRegex(text, re.compile(r"printf .*KEY", re.IGNORECASE))
        self.assertNotIn("set -x", text)


if __name__ == "__main__":
    unittest.main()
