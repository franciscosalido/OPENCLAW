-- FINLIB readiness bootstrap for fresh local PostgreSQL volumes.
-- Roles are cluster-level objects, so this file lives in initdb instead of the
-- application schema migration runner.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quimera_readonly') THEN
        CREATE ROLE quimera_readonly NOLOGIN;
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO quimera_readonly', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO quimera_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO quimera_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO quimera_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE quimera IN SCHEMA public
GRANT SELECT ON TABLES TO quimera_readonly;
