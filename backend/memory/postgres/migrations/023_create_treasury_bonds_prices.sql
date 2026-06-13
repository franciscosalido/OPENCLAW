INSERT INTO ops_data_sources (
    source_id,
    kind,
    base_url,
    license_note,
    methodology_limitations,
    enabled,
    metadata
)
VALUES (
    'tesouro_transparente',
    'treasury',
    concat(
        'https://www.tesourotransparente.gov.br/ckan/dataset/',
        'taxas-dos-titulos-ofertados-pelo-tesouro-direto'
    ),
    concat(
        'Dados publicos do Tesouro Transparente; respeitar licenca, ',
        'metadados do dataset e janela de publicacao antes de uso operacional.'
    ),
    concat(
        'Arquivo diario de precos e taxas dos titulos ofertados pelo ',
        'Tesouro Direto. Campos CSV devem ser verificados contra o catalogo ',
        'vivo antes de ingestao operacional; este schema armazena a memoria ',
        'temporal normalizada, nao o arquivo bruto.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'treasury_direct',
        'provider_dataset', 'preco_taxa_tesouro_direto'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS treasury_bonds (
    bond_id UUID PRIMARY KEY DEFAULT uuidv7(),
    bond_type TEXT NOT NULL
    CHECK (
        bond_type IN (
            'Tesouro_Selic',
            'Tesouro_IPCA+',
            'Tesouro_IPCA+_Juros_Semestrais',
            'Tesouro_Prefixado',
            'Tesouro_Prefixado_Juros_Semestrais',
            'Tesouro_Renda+',
            'Tesouro_Educa+'
        )
    ),
    security_family TEXT
    CHECK (
        security_family IS NULL
        OR security_family IN (
            'LFT',
            'LTN',
            'NTN-B',
            'NTN-B_Principal',
            'NTN-F',
            'OTHER'
        )
    ),
    maturity_date DATE NOT NULL,
    display_name TEXT NOT NULL CHECK (display_name ~ '\S'),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bond_type, maturity_date)
);

CREATE TABLE IF NOT EXISTS treasury_prices (
    bond_id UUID NOT NULL REFERENCES treasury_bonds (bond_id),
    ts TIMESTAMPTZ NOT NULL,
    price_bid NUMERIC CHECK (price_bid IS NULL OR price_bid >= 0),
    price_ask NUMERIC CHECK (price_ask IS NULL OR price_ask >= 0),
    rate_bid NUMERIC,
    rate_ask NUMERIC,
    base_value NUMERIC CHECK (base_value IS NULL OR base_value >= 0),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    PRIMARY KEY (bond_id, ts),
    CONSTRAINT uq_treasury_prices_lineage_ts UNIQUE (lineage_hash, ts),
    CHECK (
        price_bid IS NOT NULL
        OR price_ask IS NOT NULL
        OR rate_bid IS NOT NULL
        OR rate_ask IS NOT NULL
        OR base_value IS NOT NULL
    ),
    CHECK (price_ask IS NULL OR price_bid IS NULL OR price_ask >= price_bid),
    CHECK (rate_bid IS NULL OR rate_ask IS NULL OR rate_bid >= rate_ask),
    CHECK (
        ts <= date_trunc('day', now() AT TIME ZONE 'UTC') + INTERVAL '1 day'
    )
);

SELECT create_hypertable(
    'treasury_prices',
    'ts',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_treasury_bonds_type_maturity -- noqa: PG01
ON treasury_bonds (bond_type, maturity_date);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_treasury_prices_bond_ts_desc -- noqa: PG01
ON treasury_prices (bond_id, ts DESC);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_treasury_prices_source_run -- noqa: PG01
ON treasury_prices (source_id, run_id);
