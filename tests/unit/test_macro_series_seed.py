from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


SEED = Path("config/macro_series_seed.yaml")
MIGRATION = Path(
    "backend/memory/postgres/migrations/022_create_macro_catalog_observations.sql"
)
SDD = Path("docs/specs/finlib-0/pr-05-macro-library.md")

EXPECTED_SERIES = {
    "ipca",
    "igpm",
    "selic_meta",
    "selic_diaria",
    "cdi",
    "ptax_usdbrl_compra",
    "ptax_usdbrl_venda",
}
DERIVED_FX_CODES = {
    "brlusd",
    "brl_usd",
    "fx_brlusd",
    "brlusd_mid",
    "usdbrl_mid",
}
REQUIRED_SERIES_FIELDS = {
    "series_code",
    "display_name",
    "provider",
    "provider_code",
    "provider_code_status",
    "source_id",
    "unit",
    "periodicity",
    "value_type",
    "methodology_note",
}
ALLOWED_PROVIDER_CODE_STATUS = {
    "planning_reference",
    "pending_live_verification",
    "verified_live",
}
CANONICAL_LINEAGE_FIELDS = {
    "series_code",
    "ref_ts",
    "value",
    "source_id",
    "provider_code",
    "schema_version",
}


def _seed() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(SEED.read_text(encoding="utf-8")))


def _series() -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _seed()["series"])


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def test_macro_series_seed_exists_and_parses() -> None:
    assert SEED.exists()

    seed = _seed()

    assert seed["schema_version"] == 1
    assert isinstance(seed["source_policy"], dict)
    assert isinstance(seed["lineage_hash_contract"], dict)
    assert isinstance(seed["series"], list)


def test_seed_contains_exactly_the_initial_series() -> None:
    series_codes = {str(series["series_code"]) for series in _series()}

    assert series_codes == EXPECTED_SERIES
    assert series_codes.isdisjoint(DERIVED_FX_CODES)


def test_seed_series_have_required_contract_fields() -> None:
    for series in _series():
        missing = REQUIRED_SERIES_FIELDS - set(series)
        assert not missing, series["series_code"]
        for field in REQUIRED_SERIES_FIELDS:
            assert str(series[field]).strip(), (series["series_code"], field)


def test_bcb_sgs_series_are_planning_references_not_ground_truth() -> None:
    for series in _series():
        assert series["provider"] == "bcb_sgs"
        assert series["source_id"] == "bcb_sgs"
        assert series["requires_live_verification"] is True
        assert series["provider_code_status"] in ALLOWED_PROVIDER_CODE_STATUS
        assert series["provider_code_status"] != "verified_live"


def test_provider_api_pattern_and_source_policy_are_explicit() -> None:
    source_policy = cast("dict[str, Any]", _seed()["source_policy"])

    assert source_policy["provider_codes_are_ground_truth"] is False
    assert source_policy["requires_live_verification_before_ingestion"] is True
    assert "bcdata.sgs.{codigo_serie}" in str(source_policy["provider_api_pattern"])


def test_lineage_hash_contract_is_sha256_and_canonical() -> None:
    lineage = cast("dict[str, Any]", _seed()["lineage_hash_contract"])

    assert lineage["algorithm"] == "sha256"
    assert (
        set(cast("list[str]", lineage["canonical_fields"])) == CANONICAL_LINEAGE_FIELDS
    )


def test_seed_has_required_ptax_pair_without_brlusd_storage() -> None:
    series_codes = {str(series["series_code"]) for series in _series()}

    assert "ptax_usdbrl_compra" in series_codes
    assert "ptax_usdbrl_venda" in series_codes
    assert series_codes.isdisjoint(DERIVED_FX_CODES)


def test_ptax_provider_codes_follow_bcb_planning_reference_evidence() -> None:
    by_code = {str(series["series_code"]): series for series in _series()}

    assert by_code["ptax_usdbrl_compra"]["provider_code"] == "10813"
    assert by_code["ptax_usdbrl_venda"]["provider_code"] == "1"
    assert by_code["ptax_usdbrl_venda"]["provider_code"] != "10814"
    assert by_code["ptax_usdbrl_venda"]["provider_code_status"] == (
        "planning_reference"
    )
    assert by_code["ptax_usdbrl_venda"]["requires_live_verification"] is True


def test_migration_022_exists_and_is_non_destructive() -> None:
    sql = _sql().lower()

    assert MIGRATION.exists()
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "create schema" not in sql
    assert "macro." not in sql


def test_migration_scope_is_limited_to_macro_objects() -> None:
    lower_sql = _sql().lower()

    assert lower_sql.count("create table if not exists") == 2
    assert "create table if not exists macro_series_catalog" in lower_sql
    assert "create table if not exists macro_observations" in lower_sql
    assert "create or replace view vw_fx_brlusd" in lower_sql

    for forbidden in (
        "treasury_",
        "fund_registry",
        "fund_daily_info",
        "fi_instruments",
        "debenture",
        "fundamentals_",
        "repository",
        "agent",
        "pydanticai",
        "langgraph",
        "crewai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
    ):
        assert forbidden not in lower_sql


def test_migration_uses_regex_text_constraints_not_btrim() -> None:
    compact = _compact_sql()

    assert "btrim(" not in compact.lower()
    for field in (
        "display_name",
        "provider",
        "provider_code",
        "methodology_note",
        "lineage_hash",
    ):
        assert f"{field} " in compact
    assert "~ '\\S'" in compact


def test_migration_hypertable_contract() -> None:
    compact = _compact_sql()

    assert "SELECT create_hypertable(" in compact
    assert "'macro_observations'" in compact
    assert "'ref_ts'" in compact
    assert "chunk_time_interval => INTERVAL '3 months'" in compact
    assert "if_not_exists => TRUE" in compact


def test_migration_enforces_provenance_and_lineage() -> None:
    compact = _compact_sql()

    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in compact
    assert "run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id)" in compact
    assert "lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\\S')" in compact
    assert "UNIQUE (lineage_hash, ref_ts)" in compact
    assert "PRIMARY KEY (series_code, ref_ts, revision)" in compact


def test_migration_seeds_bcb_sgs_source_and_catalog_rows() -> None:
    sql = _sql()

    assert "INSERT INTO ops_data_sources" in sql
    assert "'bcb_sgs'" in sql
    assert "BCB/SGS republica series" in sql
    for series_code in EXPECTED_SERIES:
        assert f"'{series_code}'" in sql


def test_migration_does_not_store_brlusd_as_catalog_series() -> None:
    compact = _compact_sql().lower()
    catalog_insert = compact.split("insert into macro_series_catalog", maxsplit=1)[1]
    insert_section = catalog_insert.split("on conflict (series_code)", maxsplit=1)[0]

    for derived_code in DERIVED_FX_CODES:
        assert f"( '{derived_code}'," not in insert_section
        assert f"('{derived_code}'," not in insert_section


def test_view_derives_brlusd_from_ptax_latest_revision() -> None:
    compact = _compact_sql()

    assert "CREATE OR REPLACE VIEW vw_fx_brlusd AS" in compact
    assert "DISTINCT ON (series_code, ref_ts)" in compact
    assert "'ptax_usdbrl_compra'" in compact
    assert "'ptax_usdbrl_venda'" in compact
    assert "INNER JOIN latest AS venda" in compact
    assert "Guard against division by zero" in _sql()
    assert "(1 / ((compra.value + venda.value) / 2)) AS brlusd_mid" in compact


def test_sdd_documents_revision_idempotency_and_future_audit_contract() -> None:
    sdd = SDD.read_text(encoding="utf-8")

    assert "UNIQUE (lineage_hash, ref_ts)" in sdd
    assert "TimescaleDB requires unique constraints" in sdd
    assert "advisory lock keyed by" in sdd
    assert "exactly one" in sdd
    assert "audit_agent_writes" in sdd
    assert "BRL/USD is not a stored macro series" in sdd
    assert "SGS `1`" in sdd
    assert "SGS `10813`" in sdd
    assert "`10814` must not replace `1`" in sdd
    assert "Zero-valued PTAX observations" in sdd
