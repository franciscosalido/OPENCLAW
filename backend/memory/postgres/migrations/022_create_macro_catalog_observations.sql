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
    'bcb_sgs',
    'central_bank',
    'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados',
    concat(
        'Dados publicos do Banco Central do Brasil via BCData/SGS; ',
        'verificar termos, janela de consulta e metadados da serie antes ',
        'de uso operacional.'
    ),
    concat(
        'BCB/SGS republica series de diferentes fontes e metodologias. ',
        'Codigos e valores devem ser verificados contra o catalogo vivo/API ',
        'antes de ingestao operacional; revisoes retroativas devem ser ',
        'detectadas por lineage_hash e revision.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'source_family', 'macro_timeseries',
        'provider_api', 'BCData/SGS'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS macro_series_catalog (
    series_code TEXT PRIMARY KEY CHECK (
        series_code ~ '^[a-z0-9_.:-]+$'
        AND series_code NOT IN (
            'brlusd',
            'brl_usd',
            'fx_brlusd',
            'brlusd_mid',
            'usdbrl_mid'
        )
    ),
    display_name TEXT NOT NULL CHECK (display_name ~ '\S'),
    -- SQLFluff RF04: "provider" is a FINLIB domain column name.
    provider TEXT NOT NULL CHECK (provider ~ '\S'), -- noqa: RF04
    provider_code TEXT NOT NULL CHECK (provider_code ~ '\S'),
    provider_code_status TEXT NOT NULL
    CHECK (
        provider_code_status IN (
            'planning_reference',
            'pending_live_verification',
            'verified_live'
        )
    ),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    original_source TEXT CHECK (
        original_source IS NULL OR original_source ~ '\S'
    ),
    unit TEXT NOT NULL CHECK (unit ~ '\S'),
    periodicity TEXT NOT NULL
    CHECK (
        periodicity IN (
            'daily',
            'business_daily',
            'monthly',
            'annual',
            'irregular'
        )
    ),
    value_type TEXT NOT NULL
    CHECK (
        value_type IN ('index', 'rate_percent', 'fx_rate', 'level', 'other')
    ),
    methodology_note TEXT NOT NULL CHECK (methodology_note ~ '\S'),
    requires_live_verification BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        provider_code_status = 'verified_live'
        OR requires_live_verification IS TRUE
    )
);

INSERT INTO macro_series_catalog (
    series_code,
    display_name,
    provider,
    provider_code,
    provider_code_status,
    source_id,
    original_source,
    unit,
    periodicity,
    value_type,
    methodology_note,
    requires_live_verification,
    enabled,
    metadata
)
VALUES
(
    'ipca',
    'IPCA',
    'bcb_sgs',
    '433',
    'planning_reference',
    'bcb_sgs',
    'ibge',
    'percent',
    'monthly',
    'rate_percent',
    concat(
        'Codigo SGS candidato para IPCA; verificar catalogo vivo/API ',
        'BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '433')
),
(
    'igpm',
    'IGP-M',
    'bcb_sgs',
    '189',
    'planning_reference',
    'bcb_sgs',
    'fgv_ibre',
    'percent',
    'monthly',
    'rate_percent',
    concat(
        'Codigo SGS candidato para IGP-M; verificar catalogo vivo/API ',
        'BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '189')
),
(
    'selic_meta',
    'Selic meta',
    'bcb_sgs',
    '432',
    'planning_reference',
    'bcb_sgs',
    'copom',
    'percent_per_year',
    'daily',
    'rate_percent',
    concat(
        'Codigo SGS candidato para meta Selic; verificar catalogo vivo/API ',
        'BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '432')
),
(
    'selic_diaria',
    'Selic diaria',
    'bcb_sgs',
    '11',
    'planning_reference',
    'bcb_sgs',
    'bcb_demab',
    'percent_per_day',
    'business_daily',
    'rate_percent',
    concat(
        'Codigo SGS candidato para Selic diaria; verificar catalogo vivo/API ',
        'BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '11')
),
(
    'cdi',
    'CDI',
    'bcb_sgs',
    '12',
    'planning_reference',
    'bcb_sgs',
    'b3_cetip',
    'percent_per_day',
    'business_daily',
    'rate_percent',
    concat(
        'Codigo SGS candidato para CDI; verificar catalogo vivo/API ',
        'BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '12')
),
(
    'ptax_usdbrl_compra',
    'PTAX USD/BRL compra',
    'bcb_sgs',
    '10813',
    'planning_reference',
    'bcb_sgs',
    'bcb_ptax',
    'BRL_per_USD',
    'business_daily',
    'fx_rate',
    concat(
        'Codigo SGS candidato para PTAX USD/BRL compra; verificar ',
        'catalogo vivo/API BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '10813')
),
(
    'ptax_usdbrl_venda',
    'PTAX USD/BRL venda',
    'bcb_sgs',
    '1',
    'planning_reference',
    'bcb_sgs',
    'bcb_ptax',
    'BRL_per_USD',
    'business_daily',
    'fx_rate',
    concat(
        'Codigo SGS candidato para PTAX USD/BRL venda; verificar ',
        'catalogo vivo/API BCB antes de ingestao operacional.'
    ),
    TRUE,
    TRUE,
    jsonb_build_object('candidate_sgs_code', '1')
)
ON CONFLICT (series_code) DO UPDATE SET
    display_name = excluded.display_name,
    provider = excluded.provider,
    provider_code = excluded.provider_code,
    provider_code_status = excluded.provider_code_status,
    source_id = excluded.source_id,
    original_source = excluded.original_source,
    unit = excluded.unit,
    periodicity = excluded.periodicity,
    value_type = excluded.value_type,
    methodology_note = excluded.methodology_note,
    requires_live_verification = excluded.requires_live_verification,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS macro_observations (
    series_code TEXT NOT NULL REFERENCES macro_series_catalog (series_code),
    ref_ts TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    -- SQLFluff RF04: "value" is the observed macro value column.
    value NUMERIC NOT NULL, -- noqa: RF04
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    PRIMARY KEY (series_code, ref_ts, revision),
    CONSTRAINT uq_macro_observations_lineage_ref_ts
    UNIQUE (lineage_hash, ref_ts)
);

SELECT create_hypertable(
    'macro_observations',
    'ref_ts',
    chunk_time_interval => INTERVAL '3 months',
    if_not_exists => TRUE
);

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_macro_observations_series_ref_ts -- noqa: PG01,LT05
ON macro_observations (series_code, ref_ts DESC);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_macro_observations_source_run -- noqa: PG01
ON macro_observations (source_id, run_id);

CREATE OR REPLACE VIEW vw_fx_brlusd AS
WITH latest AS (
    SELECT DISTINCT ON (series_code, ref_ts)
        series_code,
        ref_ts,
        revision,
        value,
        source_id,
        run_id,
        lineage_hash
    FROM macro_observations
    WHERE
        series_code IN ('ptax_usdbrl_compra', 'ptax_usdbrl_venda')
        -- Guard against division by zero in the derived BRL/USD columns.
        AND value <> 0
    ORDER BY series_code ASC, ref_ts ASC, revision DESC
)

SELECT
    compra.ref_ts,
    compra.value AS usdbrl_bid,
    venda.value AS usdbrl_ask,
    compra.lineage_hash AS lineage_hash_bid,
    venda.lineage_hash AS lineage_hash_ask,
    compra.revision AS revision_bid,
    venda.revision AS revision_ask,
    ((compra.value + venda.value) / 2) AS usdbrl_mid,
    (1 / venda.value) AS brlusd_bid,
    (1 / compra.value) AS brlusd_ask,
    (1 / ((compra.value + venda.value) / 2)) AS brlusd_mid,
    CASE
        WHEN compra.source_id = venda.source_id THEN compra.source_id
    END AS source_id,
    CASE
        WHEN compra.run_id = venda.run_id THEN compra.run_id
    END AS run_id
FROM latest AS compra
INNER JOIN latest AS venda
    ON compra.ref_ts = venda.ref_ts
WHERE
    compra.series_code = 'ptax_usdbrl_compra'
    AND venda.series_code = 'ptax_usdbrl_venda';
