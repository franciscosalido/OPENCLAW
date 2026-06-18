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
    'cvm_informes_diarios',
    'regulator',
    'https://dados.cvm.gov.br/dataset/fi-doc-inf_diario',
    concat(
        'Dados publicos da CVM Dados Abertos; respeitar metadados, ',
        'licenca, periodicidade de atualizacao e layout vigente antes ',
        'de uso operacional.'
    ),
    concat(
        'Informes Diarios CVM sao disponibilizados como demonstrativos ',
        'por data de competencia e, desde maio de 2022, em CSV compactado. ',
        'Arquivos atualizados podem conter reapresentacoes; revision e ',
        'lineage_hash devem preservar historico de correcoes sem UPDATE ',
        'destrutivo.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'fund_daily_reports',
        'provider_dataset', 'fi-doc-inf_diario'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS fund_registry (
    fund_cnpj TEXT PRIMARY KEY CHECK (fund_cnpj ~ '^[0-9]{14}$'),
    legal_name TEXT NOT NULL CHECK (legal_name ~ '\S'),
    cvm_class TEXT CHECK (cvm_class IS NULL OR cvm_class ~ '\S'),
    fund_type TEXT CHECK (fund_type IS NULL OR fund_type ~ '\S'),
    status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (status IN ('active', 'cancelled', 'inactive', 'unknown')),
    registered_at DATE,
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fund_daily_info (
    fund_cnpj TEXT NOT NULL REFERENCES fund_registry (fund_cnpj),
    ts TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    total_portfolio_value NUMERIC
    CHECK (
        total_portfolio_value IS NULL
        OR total_portfolio_value >= 0
    ),
    quota_value NUMERIC NOT NULL CHECK (quota_value > 0),
    net_worth NUMERIC NOT NULL,
    inflow NUMERIC CHECK (inflow IS NULL OR inflow >= 0),
    outflow NUMERIC CHECK (outflow IS NULL OR outflow >= 0),
    shareholders INTEGER NOT NULL CHECK (shareholders >= 0),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    PRIMARY KEY (fund_cnpj, ts, revision),
    CONSTRAINT uq_fund_daily_info_lineage_ts UNIQUE (lineage_hash, ts)
);

SELECT create_hypertable(
    'fund_daily_info',
    'ts',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fund_registry_source_id -- noqa: PG01
ON fund_registry (source_id);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fund_daily_info_fund_ts_desc -- noqa: PG01
ON fund_daily_info (fund_cnpj, ts DESC);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fund_daily_info_source_run -- noqa: PG01
ON fund_daily_info (source_id, run_id);
