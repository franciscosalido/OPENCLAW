from __future__ import annotations

import ast
import unittest
from pathlib import Path

from backend.agent0 import domain_classifier
from backend.agent0.domain_classifier import classify_domain


FORBIDDEN_IMPORT_PREFIXES = (
    "backend.gateway",
    "backend.rag.embeddings",
    "backend.rag.retriever",
    "backend.rag.qdrant_store",
    "qdrant_client",
    "openai",
    "anthropic",
    "litellm",
    "ollama",
)


class DomainClassifierTests(unittest.TestCase):
    def test_classifier_has_no_forbidden_imports(self) -> None:
        module_path = Path(domain_classifier.__file__)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)

        for imported in imports:
            with self.subTest(imported=imported):
                self.assertFalse(
                    imported.startswith(FORBIDDEN_IMPORT_PREFIXES),
                    imported,
                )

    def test_iq_prefix_routes_to_internal(self) -> None:
        result = classify_domain("pergunta sem palavra chave", question_id="iq-001")

        self.assertEqual(result.domain, "internal")
        self.assertEqual(result.corpus, "internal")
        self.assertEqual(result.collection_name, "openclaw_internal")
        self.assertEqual(result.reason_code, "question_id_internal")

    def test_fq_prefix_routes_to_financial_collection(self) -> None:
        result = classify_domain("pergunta sem palavra chave", question_id="fq-001")

        self.assertEqual(result.corpus, "financial")
        self.assertEqual(result.collection_name, "openclaw_financial")
        self.assertEqual(result.reason_code, "question_id_financial")

    def test_keyword_selic_routes_to_macroeconomia(self) -> None:
        result = classify_domain("como a Selic afeta a inflacao?")

        self.assertEqual(result.domain, "macroeconomia")
        self.assertEqual(result.corpus, "financial")
        self.assertEqual(result.reason_code, "keyword_selic")

    def test_keyword_duration_routes_to_renda_fixa(self) -> None:
        result = classify_domain("o que e duration de renda fixa?")

        self.assertEqual(result.domain, "renda_fixa")
        self.assertEqual(result.corpus, "financial")
        self.assertEqual(result.reason_code, "keyword_duration")

    def test_keyword_ebitda_routes_to_valuation(self) -> None:
        result = classify_domain("como calcular o EBITDA?")

        self.assertEqual(result.domain, "valuation")
        self.assertEqual(result.corpus, "financial")
        self.assertEqual(result.reason_code, "keyword_ebitda")

    def test_unknown_routes_to_unknown(self) -> None:
        result = classify_domain("pergunta generica sem dominio mapeado")

        self.assertEqual(result.domain, "unknown")
        self.assertEqual(result.corpus, "none")
        self.assertEqual(result.collection_name, "none")
        self.assertEqual(result.reason_code, "no_domain_match")


if __name__ == "__main__":
    unittest.main()
