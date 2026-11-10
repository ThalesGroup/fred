-- Sets the component logins' passwords, run by the administrator right after
-- bootstrap.sql, in the same session: the chart's postgresBootstrap hook on
-- Kubernetes, make docker-prepare on Docker Compose. Passwords come from the
-- environment (CP_PASSWORD, KF_PASSWORD, RUNTIME_PASSWORD, MONITOR_PASSWORD) and
-- never appear in the server log.
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_min_duration_sample = -1;
SET log_transaction_sample_rate = 0;
SET log_min_error_statement = 'panic';
\getenv cp_password CP_PASSWORD
\getenv kf_password KF_PASSWORD
\getenv runtime_password RUNTIME_PASSWORD
\getenv monitor_password MONITOR_PASSWORD
ALTER ROLE fred_cp PASSWORD :'cp_password';
ALTER ROLE fred_kf PASSWORD :'kf_password';
ALTER ROLE fred_runtime PASSWORD :'runtime_password';
ALTER ROLE fred_monitor PASSWORD :'monitor_password';
