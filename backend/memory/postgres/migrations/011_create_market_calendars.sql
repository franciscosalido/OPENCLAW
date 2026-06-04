CREATE TABLE IF NOT EXISTS market_calendars (
    calendar_id UUID PRIMARY KEY DEFAULT uuidv7(),
    exchange TEXT NOT NULL CHECK (length(trim(exchange)) > 0),
    session_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    open_at TIMESTAMPTZ,
    close_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (is_open = FALSE)
        OR
        (open_at IS NOT NULL AND close_at IS NOT NULL AND close_at > open_at)
    ),
    UNIQUE(exchange, session_date)
);

CREATE INDEX IF NOT EXISTS idx_market_calendars_exchange_date
    ON market_calendars(exchange, session_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_calendars_is_open
    ON market_calendars(is_open);
