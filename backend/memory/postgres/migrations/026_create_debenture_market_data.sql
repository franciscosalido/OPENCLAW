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
        'Dados de mercado de debentures devem respeitar termos, licenca, ',
        'autenticacao e limites operacionais vigentes da fonte.'
    ),
    concat(
        'Taxas indicativas e PUs representam referencia de mercado ',
        'secundario. A cobertura depende de amostra, elegibilidade e ',
        'historico disponibilizado pela fonte. Ausencia de observacao nao ',
        'significa ausencia de valor economico. Acesso e janela publica ',
        'podem ser limitados. Nenhum segredo operacional e armazenado no ',
        'schema. Observacoes podem sofrer retificacao.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'coverage', jsonb_build_array('debenture'),
        'market_data_scope', 'secondary_debenture_observations'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    methodology_limitations = excluded.methodology_limitations,
    license_note = excluded.license_note,
    enabled = excluded.enabled,
    metadata = ops_data_sources.metadata || jsonb_build_object(
        'market_data_scope',
        'secondary_debenture_observations'
    );

CREATE TABLE IF NOT EXISTS debenture_market_data (
    fi_id UUID NOT NULL REFERENCES fi_instruments (instrument_id),
    ts TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    indicative_rate NUMERIC,
    pu NUMERIC CHECK (pu IS NULL OR pu > 0),
    duration INTEGER CHECK (duration IS NULL OR duration >= 0),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id),
    lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\S'),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    quality_flags JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(quality_flags) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fi_id, ts, revision),
    CONSTRAINT uq_debenture_market_data_lineage_ts UNIQUE (lineage_hash, ts),
    CHECK (
        indicative_rate IS NOT NULL OR pu IS NOT NULL OR duration IS NOT NULL
    )
);

SELECT create_hypertable(
    'debenture_market_data',
    'ts',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE OR REPLACE FUNCTION enforce_debenture_market_data_instrument_kind()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    instrument_kind TEXT;
BEGIN
    SELECT kind
    INTO instrument_kind
    FROM fi_instruments
    WHERE instrument_id = NEW.fi_id;

    IF instrument_kind IS NULL THEN
        RETURN NEW;
    END IF;

    IF instrument_kind <> 'debenture' THEN
        RAISE EXCEPTION 'debenture_market_data requires a debenture instrument';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_debenture_market_data_instrument_kind
BEFORE INSERT OR UPDATE OF fi_id ON debenture_market_data
FOR EACH ROW
EXECUTE FUNCTION enforce_debenture_market_data_instrument_kind();

-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_debenture_market_data_fi_ts_revision -- noqa: PG01,LT05
ON debenture_market_data (fi_id, ts DESC, revision DESC);
-- CONCURRENTLY is prohibited inside the transactional migration runner.
CREATE INDEX IF NOT EXISTS idx_debenture_market_data_run_id -- noqa: PG01
ON debenture_market_data (run_id);
