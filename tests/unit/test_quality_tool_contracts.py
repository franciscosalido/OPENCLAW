from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_vulture_ignores_protocol_keyword_contract_names() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    vulture = config["tool"]["vulture"]
    ignore_names = set(vulture["ignore_names"])

    assert vulture["paths"] == ["backend"]
    assert vulture["min_confidence"] == 80
    assert {
        "normalize_embeddings",
        "sentences",
        "show_progress_bar",
        "sparse_vectors_config",
        "vectors_config",
        "with_payload",
    } <= ignore_names


def test_import_linter_agent0_memory_boundary_is_configured() -> None:
    config = (ROOT / ".importlinter").read_text(encoding="utf-8")

    assert "root_package = backend" in config
    assert "Agent0 must not import memory backends directly" in config
    assert "backend.agent0" in config
    assert "backend.memory" in config
    assert "backend.working_memory" in config
    assert "backend.temporal" in config
