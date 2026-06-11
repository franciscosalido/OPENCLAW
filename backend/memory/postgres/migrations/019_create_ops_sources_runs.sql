CREATE TABLE IF NOT EXISTS ops_data_sources (
    source_id TEXT PRIMARY KEY
    CHECK (
        length(btrim(source_id)) > 0
        AND source_id ~ '^[a-z0-9_.:-]+$'
    ),
    kind TEXT NOT NULL
    CHECK (
        kind IN (
            'exchange',
            'regulator',
            'central_bank',
            'treasury',
            'market_data_vendor',
            'internal',
            'user_supplied',
            'other'
        )
    ),
    base_url TEXT,
    license_note TEXT,
    methodology_limitations TEXT NOT NULL
    CHECK (length(btrim(methodology_limitations)) > 0),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    'b3_cotacoes_historicas',
    'exchange',
    concat(
        'https://www.b3.com.br/pt_br/market-data-e-indices/',
        'servicos-de-dados/market-data/historico/mercado-a-vista/',
        'cotacoes-historicas/'
    ),
    concat(
        'Fonte pública de cotações históricas B3; respeitar termos ',
        'e metodologia da B3.'
    ),
    concat(
        'Série histórica de cotações B3 sem ajuste por inflação ou ',
        'proventos corporativos; usar com cautela para retorno total, ',
        'backtests e comparações históricas.'
    ),
    TRUE,
    jsonb_build_object(
        'country', 'BR',
        'market', 'B3',
        'source_family', 'historical_quotes'
    )
)
ON CONFLICT (source_id) DO UPDATE SET
    kind = excluded.kind,
    base_url = excluded.base_url,
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    enabled = excluded.enabled,
    metadata = excluded.metadata;

CREATE TABLE IF NOT EXISTS ops_ingestion_runs (
    run_id UUID PRIMARY KEY DEFAULT uuidv7(),
    source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id),
    agent_id TEXT NOT NULL CHECK (length(btrim(agent_id)) > 0),
    mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'execute')), -- noqa: RF04
    status TEXT NOT NULL
    CHECK (
        status IN ('created', 'running', 'completed', 'failed', 'cancelled')
    ),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    records_updated INTEGER NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    source_snapshot_hash TEXT
    CHECK (
        source_snapshot_hash IS NULL
        OR length(btrim(source_snapshot_hash)) > 0
    ),
    error_summary TEXT CHECK (
        error_summary IS NULL OR length(btrim(error_summary)) > 0
    ),
    trace_id UUID NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (
        NOT (mode = 'execute' AND status = 'completed')
        OR nullif(btrim(source_snapshot_hash), '') IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_ops_ingestion_runs_source_started_at -- noqa: PG01,LT05
ON ops_ingestion_runs (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_ingestion_runs_trace_id -- noqa: PG01
ON ops_ingestion_runs (trace_id);
CREATE INDEX IF NOT EXISTS idx_ops_ingestion_runs_status_started_at -- noqa: PG01,LT05
ON ops_ingestion_runs (status, started_at DESC);
