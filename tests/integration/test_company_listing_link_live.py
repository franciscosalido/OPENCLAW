from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_company_listing") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    await run_migrations(client)


async def _insert_company(
    client: PostgresClient,
    *,
    cnpj: str = "33000167000101",
    cnpj_base: str = "33000167",
    lineage_hash: str = "sha256:company-petrobras",
) -> UUID:
    company_id = await client.pool.fetchval(
        """
        INSERT INTO company_registry(
            cnpj, cnpj_base, legal_name, trade_name, cvm_code, source_id,
            lineage_hash
        )
        VALUES(
            $1, $2, 'PETROLEO BRASILEIRO S.A. PETROBRAS', 'PETROBRAS',
            '9512', 'cvm_cia_aberta_cadastro', $3
        )
        RETURNING company_id
        """,
        cnpj,
        cnpj_base,
        lineage_hash,
    )
    return UUID(str(company_id))


async def _insert_listing(
    client: PostgresClient,
    *,
    company_id: UUID,
    ticker: str,
    share_class: str,
    isin: str | None,
    lineage_hash: str,
    exchange: str = "B3",
) -> UUID:
    listing_id = await client.pool.fetchval(
        """
        INSERT INTO company_listings(
            company_id, exchange, ticker, share_class, isin, source_id,
            lineage_hash
        )
        VALUES($1, $2, $3, $4, $5, 'b3_listings', $6)
        RETURNING listing_id
        """,
        company_id,
        exchange,
        ticker,
        share_class,
        isin,
        lineage_hash,
    )
    return UUID(str(listing_id))


async def test_petr3_petr4_resolve_to_same_company(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    company_id = await _insert_company(postgres_client)

    petr3 = await _insert_listing(
        postgres_client,
        company_id=company_id,
        ticker="PETR3",
        share_class="ON",
        isin="BRPETRACNOR9",
        lineage_hash="sha256:petr3-listing",
    )
    petr4 = await _insert_listing(
        postgres_client,
        company_id=company_id,
        ticker="PETR4",
        share_class="PN",
        isin="BRPETRACNPR6",
        lineage_hash="sha256:petr4-listing",
    )

    rows = await postgres_client.pool.fetch(
        """
        SELECT ticker, listing_id, company_id
        FROM company_listings
        WHERE ticker IN ('PETR3', 'PETR4')
        ORDER BY ticker
        """
    )

    assert petr3 != petr4
    assert [(row["ticker"], row["company_id"]) for row in rows] == [
        ("PETR3", company_id),
        ("PETR4", company_id),
    ]
    resolved = await postgres_client.pool.fetchval(
        "SELECT company_id FROM company_listings WHERE ticker = 'PETR4'"
    )
    assert resolved == company_id


async def test_company_listing_constraints_are_enforced(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    company_id = await _insert_company(postgres_client)

    await _insert_listing(
        postgres_client,
        company_id=company_id,
        ticker="PETR3",
        share_class="ON",
        isin="BRPETRACNOR9",
        lineage_hash="sha256:petr3-listing",
    )
    with pytest.raises(UniqueViolationError):
        await _insert_listing(
            postgres_client,
            company_id=company_id,
            ticker="PETR3",
            share_class="ON",
            isin=None,
            lineage_hash="sha256:petr3-duplicate",
        )
    await _insert_listing(
        postgres_client,
        company_id=company_id,
        ticker="PETR3",
        share_class="ON",
        isin=None,
        lineage_hash="sha256:petr3-nyse",
        exchange="NYSE",
    )
    with pytest.raises(CheckViolationError):
        await _insert_listing(
            postgres_client,
            company_id=company_id,
            ticker="PETRA",
            share_class="ON",
            isin=None,
            lineage_hash="sha256:bad-ticker",
        )
    with pytest.raises(CheckViolationError):
        await _insert_listing(
            postgres_client,
            company_id=company_id,
            ticker="PETR5",
            share_class="BAD",
            isin=None,
            lineage_hash="sha256:bad-share-class",
        )
    with pytest.raises(CheckViolationError):
        await _insert_listing(
            postgres_client,
            company_id=company_id,
            ticker="PETR6",
            share_class="PN",
            isin="bad",
            lineage_hash="sha256:bad-isin",
        )


async def test_company_registry_constraints_are_enforced(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(CheckViolationError):
        await _insert_company(
            postgres_client,
            cnpj="33.000.167/0001-01",
            cnpj_base="33000167",
            lineage_hash="sha256:punctuated-cnpj",
        )
    with pytest.raises(CheckViolationError):
        await _insert_company(
            postgres_client,
            cnpj="33000167000101",
            cnpj_base="33000168",
            lineage_hash="sha256:bad-cnpj-base",
        )
    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO company_registry(
                cnpj, cnpj_base, legal_name, source_id, lineage_hash
            )
            VALUES(
                '11222333000181', '11222333', 'Missing Source SA',
                'missing_source', 'sha256:missing-source'
            )
            """
        )
    company_id = await _insert_company(postgres_client)
    with pytest.raises(UniqueViolationError):
        await _insert_company(
            postgres_client,
            cnpj="44000167000101",
            cnpj_base="44000167",
            lineage_hash="sha256:company-petrobras",
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO company_listings(
                company_id, exchange, ticker, share_class, source_id,
                lineage_hash, metadata
            )
            VALUES(
                $1, 'B3', 'VALE3', 'ON', 'b3_listings',
                'sha256:bad-metadata', '[]'::jsonb
            )
            """,
            company_id,
        )


async def test_level0_fields_do_not_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    rows = await postgres_client.pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name IN (
            'company_registry',
            'company_listings',
            'fundamentals_statements',
            'fundamentals_indicators'
        )
        """
    )
    names = {str(row["column_name"]) for row in rows}

    assert not names.intersection(
        {
            "quantity",
            "position_size",
            "acquisition_price",
            "cost_basis",
            "account_number",
            "portfolio_id",
            "user_id",
        }
    )
