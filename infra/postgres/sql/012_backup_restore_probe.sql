-- PR-09 restore verification probe. Safe to run in the temporary restore DB.

SELECT 1 AS restore_probe_ok;

SELECT to_regclass('public.sessions') IS NOT NULL AS sessions_present;
SELECT to_regclass('public.turns') IS NOT NULL AS turns_present;
SELECT to_regclass('public.agent_states') IS NOT NULL AS agent_states_present;
SELECT
    to_regclass('public.entity_mentions') IS NOT NULL
        AS entity_mentions_present;

SELECT extname
FROM pg_extension
WHERE extname IN ('pg_stat_statements', 'vector', 'timescaledb')
ORDER BY extname;
