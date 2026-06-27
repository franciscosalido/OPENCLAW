CREATE OR REPLACE FUNCTION prevent_debenture_market_data_kind_drift()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.kind = 'debenture'
        AND NEW.kind <> 'debenture'
        AND EXISTS (
            SELECT 1
            FROM debenture_market_data
            WHERE fi_id = OLD.instrument_id
        )
    THEN
        RAISE EXCEPTION
            'cannot change fi_instruments.kind while debenture_market_data rows exist';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_fi_instruments_debenture_market_data_kind_guard
BEFORE UPDATE OF kind ON fi_instruments
FOR EACH ROW
WHEN (old.kind IS DISTINCT FROM new.kind)
EXECUTE FUNCTION prevent_debenture_market_data_kind_drift();
