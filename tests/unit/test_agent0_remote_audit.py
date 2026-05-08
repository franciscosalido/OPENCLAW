from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Any, cast

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_REMOTE_IMPORTS = (
    "openai",
    "anthropic",
    "google.generativeai",
    "gemini",
    "openrouter",
    "azure.ai",
)
PUBLIC_AGENT0_MODULES = (
    REPO_ROOT / "backend" / "agent0" / "openclaw.py",
    REPO_ROOT / "scripts" / "openclaw.py",
)


class Agent0RemoteAuditTests(unittest.TestCase):
    def test_public_agent0_modules_do_not_import_remote_provider_sdks(self) -> None:
        for module_path in PUBLIC_AGENT0_MODULES:
            imports = _imports(module_path)
            for imported in imports:
                with self.subTest(module=str(module_path), imported=imported):
                    self.assertFalse(imported.startswith(FORBIDDEN_REMOTE_IMPORTS))

    def test_remote_config_disabled_and_aliases_local_only(self) -> None:
        rag_config = yaml.safe_load(
            (REPO_ROOT / "config" / "rag_config.yaml").read_text(encoding="utf-8")
        )
        gateway_config = yaml.safe_load(
            (REPO_ROOT / "config" / "litellm_config.yaml").read_text(encoding="utf-8")
        )
        rag = cast(dict[str, Any], rag_config)
        gateway = cast(dict[str, Any], rag["gateway"])
        routing = cast(dict[str, Any], gateway["routing"])
        self.assertFalse(routing["remote_enabled"])

        litellm = cast(dict[str, Any], gateway_config)
        model_list = cast(list[dict[str, Any]], litellm["model_list"])
        for item in model_list:
            params = cast(dict[str, Any], item["litellm_params"])
            api_base = str(params.get("api_base", ""))
            self.assertTrue(
                api_base.startswith(("http://localhost:", "http://127.0.0.1:")),
                api_base,
            )

    def test_rollback_doc_only_deletes_agent0_collections(self) -> None:
        text = (REPO_ROOT / "docs" / "AGENT0_ROLLBACK.md").read_text(encoding="utf-8")

        self.assertIn("qdrant collection delete openclaw_internal", text)
        self.assertIn("qdrant collection delete openclaw_financial", text)
        self.assertIn("Do not delete `openclaw_knowledge`", text)
        self.assertNotIn("qdrant collection delete openclaw_knowledge", text)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return imports


if __name__ == "__main__":
    unittest.main()
