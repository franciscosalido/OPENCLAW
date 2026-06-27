INSERT INTO ops_data_sources (
    source_id,
    kind,
    base_url,
    license_note,
    methodology_limitations,
    enabled,
    metadata
)
VALUES
(
    'cvm_cia_aberta_cadastro',
    'regulator',
    'https://dados.cvm.gov.br/dataset/cia_aberta-cad',
    concat(
        'Dados cadastrais publicos da CVM Dados Abertos; verificar ',
        'metadados, layout e periodicidade antes de uso operacional.'
    ),
    concat(
        'Cadastro de companhias abertas pode conter situacao cadastral, ',
        'CNPJ e datas de registro. Alteracoes e cancelamentos devem ser ',
        'tratados como historico regulatorio, nao como recomendacao.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'company_registry',
        'provider_dataset', 'cia_aberta-cad'
    )
),
(
    'cvm_dfp',
    'regulator',
    'https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp',
    concat(
        'Dados publicos DFP da CVM Dados Abertos; respeitar metadados, ',
        'layout, licenca e periodicidade vigente.'
    ),
    concat(
        'DFP contem demonstracoes financeiras anuais de companhias abertas. ',
        'Arquivos podem ser reapresentados; version e prior_version_id devem ',
        'preservar historico sem UPDATE destrutivo.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'fundamentals_statements',
        'period_type', 'DFP'
    )
),
(
    'cvm_itr',
    'regulator',
    'https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr',
    concat(
        'Dados publicos ITR da CVM Dados Abertos; respeitar metadados, ',
        'layout, licenca e periodicidade vigente.'
    ),
    concat(
        'ITR contem demonstracoes financeiras trimestrais de companhias ',
        'abertas. Arquivos podem ser reapresentados; version e ',
        'prior_version_id devem preservar historico sem UPDATE destrutivo.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'fundamentals_statements',
        'period_type', 'ITR'
    )
),
(
    'b3_listings',
    'exchange',
    'https://www.b3.com.br/',
    concat(
        'Dados publicos de listagens B3; ticker, classe e ISIN sao ',
        'identificadores de listagem, nao identidade canonica da companhia.'
    ),
    concat(
        'Listagens podem mudar por reorganizacao societaria, cancelamento, ',
        'conversao de classe ou alteracao operacional. PETR3 e PETR4 podem ',
        'apontar para a mesma companhia canonica.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'market', 'B3',
        'source_family', 'company_listings'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    metadata = ops_data_sources.metadata || excluded.metadata;

CREATE TABLE IF NOT EXISTS company_registry (
    company_id UUID PRIMARY KEY DEFAULT uuidv7(),
    cnpj TEXT NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
    cnpj_base TEXT NOT NULL CHECK (cnpj_base ~ '^[0-9]{8}$'),
    legal_name TEXT NOT NULL CHECK (legal_name ~ '\S'),
    trade_name TEXT CHECK (trade_name IS NULL OR trade_name ~ '\S'),
    sector_ibge TEXT CHECK (sector_ibge IS NULL OR sector_ibge ~ '\S'),
    cvm_code TEXT UNIQUE CHECK (cvm_code IS NULL OR cvm_code ~ '\S'),
    cvm_category TEXT CHECK (cvm_category IS NULL OR cvm_category ~ '\S'),
    listing_status TEXT NOT NULL DEFAULT 'listed'
    CHECK (
        listing_status IN (
            'listed',
            'suspended',
            'delisted',
            'cancelled',
            'unknown'
        )
    ),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    lineage_hash TEXT NOT NULL UNIQUE CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (cnpj_base = substring(cnpj FROM 1 FOR 8))
);

CREATE TABLE IF NOT EXISTS company_listings (
    listing_id UUID PRIMARY KEY DEFAULT uuidv7(),
    company_id UUID NOT NULL REFERENCES company_registry (company_id),
    exchange TEXT NOT NULL
    CHECK (exchange IN ('B3', 'NYSE', 'NASDAQ', 'OTHER')),
    ticker TEXT NOT NULL CHECK (ticker ~ '^[A-Z]{4}[0-9]{1,2}$'),
    share_class TEXT NOT NULL
    CHECK (share_class IN ('ON', 'PN', 'UNT', 'BDR', 'OTHER')),
    isin TEXT UNIQUE
    CHECK (isin IS NULL OR isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
    lot_size INTEGER NOT NULL DEFAULT 100 CHECK (lot_size > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    listed_at DATE,
    delisted_at DATE,
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    lineage_hash TEXT NOT NULL UNIQUE CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange, ticker),
    CHECK (
        delisted_at IS NULL
        OR listed_at IS NULL
        OR delisted_at >= listed_at
    )
);

CREATE TABLE IF NOT EXISTS fundamentals_statements (
    statement_id UUID PRIMARY KEY DEFAULT uuidv7(),
    company_id UUID NOT NULL REFERENCES company_registry (company_id),
    period_type TEXT NOT NULL CHECK (period_type IN ('DFP', 'ITR')),
    period_kind TEXT NOT NULL CHECK (period_kind IN ('annual', 'quarterly')),
    statement_scope TEXT NOT NULL
    CHECK (statement_scope IN ('consolidated', 'individual')),
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 1990 AND 2100),
    fiscal_quarter INTEGER
    CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4),
    period_end DATE NOT NULL,
    filing_date DATE NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1), -- noqa: RF04
    restatement_reason TEXT
    CHECK (restatement_reason IS NULL OR restatement_reason ~ '\S'),
    prior_version_id UUID REFERENCES fundamentals_statements (statement_id),
    statements_json JSONB NOT NULL
    CHECK (jsonb_typeof(statements_json) = 'object'),
    currency TEXT NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
    unit_multiplier INTEGER NOT NULL DEFAULT 1000
    CHECK (unit_multiplier IN (1, 1000, 1000000)),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL UNIQUE CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        company_id,
        period_type,
        period_kind,
        statement_scope,
        period_end,
        version
    ),
    CHECK (
        (
            period_type = 'DFP'
            AND period_kind = 'annual'
            AND fiscal_quarter IS NULL
        )
        OR (
            period_type = 'ITR'
            AND period_kind = 'quarterly'
            AND fiscal_quarter BETWEEN 1 AND 4
        )
    ),
    CHECK (
        (
            version = 1
            AND prior_version_id IS NULL
            AND restatement_reason IS NULL
        )
        OR (
            version > 1
            AND prior_version_id IS NOT NULL
            AND restatement_reason IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS fundamentals_indicators (
    company_id UUID NOT NULL REFERENCES company_registry (company_id),
    ts TIMESTAMPTZ NOT NULL,
    indicator_set TEXT NOT NULL
    CHECK (indicator_set IN ('quarterly', 'trailing_12m', 'annual')),
    source_statement_id UUID NOT NULL
    REFERENCES fundamentals_statements (statement_id),
    indicators_json JSONB NOT NULL
    CHECK (jsonb_typeof(indicators_json) = 'object'),
    computation_hash TEXT NOT NULL CHECK (computation_hash ~ '\S'),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, ts, indicator_set, source_statement_id),
    CONSTRAINT uq_fundamentals_indicators_lineage_ts UNIQUE (lineage_hash, ts)
);

SELECT create_hypertable(
    'fundamentals_indicators',
    'ts',
    chunk_time_interval => INTERVAL '3 months',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_company_registry_cnpj_base -- noqa: PG01
ON company_registry (cnpj_base);
CREATE INDEX IF NOT EXISTS idx_company_registry_cvm_code -- noqa: PG01
ON company_registry (cvm_code);
CREATE INDEX IF NOT EXISTS idx_company_listings_company_id -- noqa: PG01
ON company_listings (company_id);
CREATE INDEX IF NOT EXISTS idx_fundamentals_statements_company_period -- noqa: PG01,LT05
ON fundamentals_statements (company_id, period_end DESC, version DESC);
CREATE INDEX IF NOT EXISTS idx_fundamentals_indicators_company_ts -- noqa: PG01,LT05
ON fundamentals_indicators (company_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_fundamentals_indicators_statement -- noqa: PG01
ON fundamentals_indicators (source_statement_id);
