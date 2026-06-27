from __future__ import annotations

import inspect
from pathlib import Path

from backend.finlib.repositories import (
    TreasuryBondInput,
    TreasuryPriceInput,
    TreasuryRepository,
)


SOURCE = Path("backend/finlib/repositories/treasury_repository.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_treasury_repository_public_methods_are_async() -> None:
    assert inspect.iscoroutinefunction(TreasuryRepository.upsert_bonds_batch)
    assert inspect.iscoroutinefunction(TreasuryRepository.upsert_prices_batch)


def test_treasury_repository_uses_dtos() -> None:
    bond = TreasuryBondInput(
        bond_type="Tesouro_Selic",
        maturity_date="2029-03-01",
        display_name="Tesouro Selic 2029",
        source_id="tesouro_transparente",
    )
    price = TreasuryPriceInput(
        bond_id="00000000-0000-7000-8000-000000000001",
        ts="2026-01-02T00:00:00+00:00",
        source_id="tesouro_transparente",
        run_id="00000000-0000-7000-8000-000000000002",
        lineage_hash="sha256:treasury-price",
        price_bid="1000.00",
    )

    assert bond.bond_type == "Tesouro_Selic"
    assert price.lineage_hash == "sha256:treasury-price"


def test_treasury_bonds_use_natural_key_and_preserve_bond_id() -> None:
    source = _source()

    assert "ON CONFLICT (bond_type, maturity_date)" in source
    assert "RETURNING bond_id" in source


def test_treasury_prices_use_schema_aligned_idempotency() -> None:
    source = _source()

    assert "ON CONFLICT (lineage_hash, ts) DO NOTHING" in source
    assert "PRIMARY KEY (bond_id, ts)" not in source


def test_treasury_empty_batch_policy_is_noop_without_audit() -> None:
    assert "return BatchWriteResult.empty()" in _source()


def test_treasury_repository_has_no_csv_parser_or_remote_fetch() -> None:
    source = _source().lower()
    for forbidden in ("csv", "httpx", "requests", "sqlalchemy", "sqlmodel", "alembic"):
        assert forbidden not in source
