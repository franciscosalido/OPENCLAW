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
    'local_fixed_income_input',
    'user_supplied',
    NULL,
    concat(
        'Entrada local fornecida pelo usuario para catalogo declarativo ',
        'de renda fixa privada brasileira.'
    ),
    concat(
        'CDB, LCA e LCI tipicamente entram por extrato local, banco ou ',
        'corretora. Quando houver posicao do usuario, saldo, conta ',
        'ou identificador pessoal, o dado e Level 0 e nao deve ser enviado a ',
        'provedores remotos. Este PR modela apenas catalogo de instrumentos.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'coverage', jsonb_build_array('cdb', 'lca', 'lci'),
        'level0', TRUE
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

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
    'anbima_debentures',
    'market_data_vendor',
    'https://developers.anbima.com.br/',
    concat(
        'ANBIMA pode publicar dados de mercado para debentures, CRI e ',
        'CRA em escopos futuros; respeitar autenticacao, licenca e ',
        'termos vigentes.'
    ),
    concat(
        'Fonte semipublica para escopos futuros de debentures, CRI e CRA. ',
        'Esta migration nao consulta provedores, nao substitui fontes ',
        'oficiais e registra somente a origem declarativa do catalogo.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'coverage', jsonb_build_array('cri', 'cra', 'debenture'),
        'level0', FALSE
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS fi_instruments (
    instrument_id UUID PRIMARY KEY DEFAULT uuidv7(),
    kind TEXT NOT NULL
    CHECK (kind IN ('cdb', 'lca', 'lci', 'cri', 'cra', 'debenture')),
    issuer_cnpj TEXT NOT NULL CHECK (issuer_cnpj ~ '^[0-9]{14}$'),
    issuer_name TEXT NOT NULL CHECK (issuer_name ~ '\S'),
    instrument_name TEXT CHECK (
        instrument_name IS NULL OR instrument_name ~ '\S'
    ),
    isin TEXT UNIQUE
    CHECK (isin IS NULL OR isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
    indexer TEXT NOT NULL CHECK (
        indexer IN ('cdi', 'ipca', 'prefixado', 'selic', 'igpm')
    ),
    rate_spec JSONB NOT NULL CHECK (
        jsonb_typeof(rate_spec) = 'object'
        AND rate_spec ? 'indexer'
        AND rate_spec ? 'rate_model'
        AND rate_spec ? 'day_count'
        AND rate_spec ? 'payment_frequency'
    ),
    fgc_covered BOOLEAN NOT NULL DEFAULT FALSE,
    issue_date DATE,
    maturity_date DATE,
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lineage_hash),
    CHECK (
        kind NOT IN ('cri', 'cra', 'debenture') OR fgc_covered = FALSE
    ),
    CHECK (
        kind NOT IN ('cri', 'cra', 'debenture')
        OR maturity_date IS NOT NULL
    ),
    CHECK (
        maturity_date IS NULL
        OR issue_date IS NULL
        OR maturity_date >= issue_date
    )
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fi_instruments_kind_indexer -- noqa: PG01
ON fi_instruments (kind, indexer);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fi_instruments_issuer_cnpj -- noqa: PG01
ON fi_instruments (issuer_cnpj);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_fi_instruments_source_id -- noqa: PG01
ON fi_instruments (source_id);
