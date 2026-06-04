CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id      UUID NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
    entity_text  TEXT NOT NULL CHECK (length(trim(entity_text)) > 0),
    entity_type  TEXT NOT NULL CHECK (length(trim(entity_type)) > 0),
    start_char   INTEGER NOT NULL CHECK (start_char >= 0),
    end_char     INTEGER NOT NULL CHECK (end_char >= start_char),
    confidence   DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))
);

CREATE INDEX IF NOT EXISTS idx_entity_mentions_turn_id
    ON entity_mentions(turn_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_text
    ON entity_mentions(entity_text);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_type
    ON entity_mentions(entity_type);
