from __future__ import annotations

from pathlib import Path


DATA_DICTIONARY = Path("docs/data/DATA_DICTIONARY.md")

REQUIRED_OBJECTS = (
    "ops_data_sources",
    "ops_ingestion_runs",
    "ops_ingestion_watermarks",
    "ops_data_quality_checks",
    "ops_outbox_events",
    "audit_agent_writes",
    "macro_series_catalog",
    "macro_observations",
    "macro_observations_latest_revision",
    "treasury_bonds",
    "treasury_prices",
    "treasury_latest_prices_view",
    "fund_registry",
    "fund_daily_info",
    "fund_daily_info_latest_revision",
    "fund_monthly_quota_returns",
    "fi_instruments",
    "debenture_market_data",
    "company_registry",
    "company_listings",
    "fundamentals_statements",
    "fundamentals_indicators",
    "market_bars",
    "market_bars_1d_cagg",
    "market_bars_1d",
    "vw_kronos_ohlcva_input",
)

REQUIRED_FIELDS = (
    "Type:",
    "Primary key:",
    "Natural key:",
    "Provenance:",
    "Revision/version semantics:",
    "Hypertable:",
    "Continuous aggregate:",
    "Compression:",
    "Retention:",
    "Repository:",
    "Future data agent:",
    "Level 0 risk:",
    "Kronos relevance:",
)


def _text() -> str:
    return DATA_DICTIONARY.read_text(encoding="utf-8")


def _section(text: str, object_name: str) -> str:
    marker = f"### {object_name}"
    start = text.index(marker)
    next_start = text.find("\n### ", start + len(marker))
    if next_start == -1:
        return text[start:]
    return text[start:next_start]


def test_data_dictionary_exists_and_mentions_required_objects() -> None:
    text = _text()

    for object_name in REQUIRED_OBJECTS:
        assert f"### {object_name}" in text


def test_every_object_section_has_required_contract_fields() -> None:
    text = _text()

    for object_name in REQUIRED_OBJECTS:
        section = _section(text, object_name)
        for field in REQUIRED_FIELDS:
            assert field in section, f"{object_name} missing {field}"


def test_future_objects_are_marked_future_not_current() -> None:
    text = _text()

    assert "The following are FUTURE" in text
    assert "FUTURE `model_runs` writes" in text
    assert "FUTURE `kronos_forecasts` writes" in text
    assert "FUTURE data agents" in text
