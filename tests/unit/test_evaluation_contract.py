"""Contract tests for the Sprint RAG-1A evaluation benchmark."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, cast

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "evaluation"
BENCHMARK_FILE = EVAL_DIR / "benchmark_queries.yaml"
EXPECTED_RESULTS_FILE = EVAL_DIR / "expected_results.yaml"
GITIGNORE_FILE = REPO_ROOT / ".gitignore"
GITKEEP_FILE = EVAL_DIR / "results" / ".gitkeep"

MIN_QUERY_COUNT = 28
REQUIRED_FIELDS = frozenset(
    {"id", "query", "category", "expected_doc_ids", "expected_terms"}
)
VALID_CATEGORIES = frozenset(
    {"ticker", "fii", "renda_fixa", "macro_br", "estrategia", "siglas", "multilingual"}
)
CATEGORY_PREFIX_MAP = {
    "ticker": "TICKER",
    "fii": "FII",
    "renda_fixa": "RENDA_FIXA",
    "macro_br": "MACRO_BR",
    "estrategia": "STRAT",
    "siglas": "SIGLA",
    "multilingual": "MULTI",
}
ID_PATTERN = re.compile(r"^(TICKER|FII|RENDA_FIXA|MACRO_BR|STRAT|SIGLA|MULTI)_\d{3}$")
CORPUS_ANCHOR_PATTERN = re.compile(
    r"\b(documento sintético|corpus sintético)\b",
    re.IGNORECASE,
)
LOCAL_DETAIL_PATTERN = re.compile(
    r"\b("
    r"alerta|bloco|cenário|cláusula|critério|filtro|gatilho|hipótese|janela|"
    r"limite|marcador|matriz|nota|postura|proxy|regra|régua|sinal|tratamento|trilha"
    r")\b",
    re.IGNORECASE,
)
PARAMETRIC_QUERY_PATTERN = re.compile(
    r"\b("
    r"o que (é|e)|como calcular|como a selic afeta|defina|explique o conceito|"
    r"qual a diferença entre"
    r")\b",
    re.IGNORECASE,
)

Query = dict[str, object]


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _query_text(query: Query, field: str) -> str:
    value = query[field]
    if not isinstance(value, str):
        raise AssertionError(f"{query.get('id', '?')} field {field} must be a string")
    return value


def _query_list(query: Query, field: str) -> list[object]:
    value = query[field]
    if not isinstance(value, list):
        raise AssertionError(f"{query.get('id', '?')} field {field} must be a list")
    return value


def _load_queries() -> list[Query]:
    raw = _load_yaml(BENCHMARK_FILE)
    if not isinstance(raw, list):
        raise AssertionError("benchmark_queries.yaml must contain a YAML list")

    queries: list[Query] = []
    for item in raw:
        if not isinstance(item, dict):
            raise AssertionError("Each benchmark query must be a mapping")
        queries.append(cast(Query, item))
    return queries


class EvaluationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.queries = _load_queries()

    queries: list[Query]

    def test_benchmark_queries_min_count(self) -> None:
        self.assertGreaterEqual(
            len(self.queries),
            MIN_QUERY_COUNT,
            f"Mínimo {MIN_QUERY_COUNT} queries. Encontradas: {len(self.queries)}",
        )

    def test_all_queries_have_required_fields(self) -> None:
        for query in self.queries:
            missing = REQUIRED_FIELDS - query.keys()
            self.assertFalse(
                missing,
                f"Query {query.get('id', '?')} sem campos obrigatórios: {sorted(missing)}",
            )

    def test_all_categories_are_valid(self) -> None:
        for query in self.queries:
            category = _query_text(query, "category")
            self.assertIn(category, VALID_CATEGORIES, f"Categoria inválida: {category}")

    def test_ids_are_unique(self) -> None:
        ids = [_query_text(query, "id") for query in self.queries]
        self.assertEqual(len(ids), len(set(ids)), "IDs duplicados encontrados")

    def test_id_format_matches_category(self) -> None:
        for query in self.queries:
            query_id = _query_text(query, "id")
            category = _query_text(query, "category")
            expected_prefix = CATEGORY_PREFIX_MAP[category]
            actual_prefix = query_id.rsplit("_", 1)[0]

            self.assertRegex(query_id, ID_PATTERN, f"ID inválido: {query_id}")
            self.assertEqual(
                actual_prefix,
                expected_prefix,
                f"ID {query_id} não bate com categoria {category}",
            )

    def test_expected_terms_not_empty(self) -> None:
        for query in self.queries:
            expected_terms = _query_list(query, "expected_terms")
            self.assertTrue(expected_terms, f"expected_terms vazio em {query['id']}")

    def test_expected_doc_ids_not_empty(self) -> None:
        for query in self.queries:
            expected_doc_ids = _query_list(query, "expected_doc_ids")
            self.assertTrue(expected_doc_ids, f"expected_doc_ids vazio em {query['id']}")

    def test_results_gitignore_exists(self) -> None:
        content = GITIGNORE_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "evaluation/results/*.json",
            content,
            ".gitignore não protege resultados JSON de evaluation/results/",
        )
        self.assertIn(
            "evaluation/results/*.csv",
            content,
            ".gitignore não protege resultados CSV de evaluation/results/",
        )
        self.assertIn(
            "evaluation/results/*.txt",
            content,
            ".gitignore não protege resultados TXT de evaluation/results/",
        )

    def test_results_gitkeep_exists(self) -> None:
        self.assertTrue(GITKEEP_FILE.exists(), "evaluation/results/.gitkeep não existe")

    def test_expected_results_yaml_parseable(self) -> None:
        data = _load_yaml(EXPECTED_RESULTS_FILE)
        self.assertIsInstance(data, dict, "expected_results.yaml deve ser um mapping")
        self.assertGreater(len(data), 0, "expected_results.yaml está vazio")

    def test_all_queries_are_anchored_to_synthetic_local_corpus(self) -> None:
        for query in self.queries:
            query_text = _query_text(query, "query")
            self.assertRegex(
                query_text,
                CORPUS_ANCHOR_PATTERN,
                f"{query['id']} deve depender do corpus sintético local",
            )

    def test_queries_reject_parametric_definition_shape(self) -> None:
        for query in self.queries:
            query_text = _query_text(query, "query")
            self.assertNotRegex(
                query_text,
                PARAMETRIC_QUERY_PATTERN,
                f"{query['id']} parece pergunta paramétrica, não teste de retrieval",
            )

    def test_all_queries_include_local_adversarial_detail_marker(self) -> None:
        for query in self.queries:
            query_text = _query_text(query, "query")
            self.assertRegex(
                query_text,
                LOCAL_DETAIL_PATTERN,
                f"{query['id']} precisa de detalhe local verificável",
            )

    def test_expected_results_cover_every_expected_doc_id(self) -> None:
        data = _load_yaml(EXPECTED_RESULTS_FILE)
        if not isinstance(data, dict):
            raise AssertionError("expected_results.yaml deve ser um mapping")

        for query in self.queries:
            query_id = _query_text(query, "id")
            expected_doc_ids = {str(doc_id) for doc_id in _query_list(query, "expected_doc_ids")}
            graded_results = data.get(query_id)
            if not isinstance(graded_results, dict):
                raise AssertionError(f"{query_id} não existe em expected_results.yaml")

            missing_doc_ids = expected_doc_ids - set(graded_results)
            self.assertFalse(
                missing_doc_ids,
                f"{query_id} sem relevance grade para: {sorted(missing_doc_ids)}",
            )
