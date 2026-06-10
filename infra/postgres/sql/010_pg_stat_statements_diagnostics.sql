-- PR-09 operational diagnostics for pg_stat_statements.
-- Query text is intentionally omitted by default.

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
WHERE name = 'pg_stat_statements';

SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';

SELECT current_setting('shared_preload_libraries') AS shared_preload_libraries;
SELECT current_setting('compute_query_id') AS compute_query_id;
SELECT current_setting('pg_stat_statements.max') AS pg_stat_statements_max;
SELECT current_setting('pg_stat_statements.track') AS pg_stat_statements_track;
SELECT current_setting('track_io_timing') AS track_io_timing;

SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blk_read_time,
    shared_blk_write_time
FROM pg_stat_statements(showtext := false)
ORDER BY mean_exec_time DESC
LIMIT 10;
