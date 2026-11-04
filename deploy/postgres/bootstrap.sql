-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Admin only: psql -X -v ON_ERROR_STOP=1 -v database=fred -d fred -f bootstrap.sql
-- Passwords are supplied separately by deployment, never in this file.
-- Serialize invocations per cluster in the deployment orchestrator.
\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(66723001);
SELECT set_config('fred.bootstrap_database', :'database', true);
DO $bootstrap$
DECLARE name text;
BEGIN
    IF current_database() <> current_setting('fred.bootstrap_database') THEN
        RAISE EXCEPTION 'bootstrap must connect to the requested database';
    END IF;
    FOREACH name IN ARRAY ARRAY['fred_cp', 'fred_kf', 'fred_runtime', 'fred_monitor',
        'fred_kf_reader', 'fred_runtime_reader', 'fred_monitor_reader'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = name) THEN
            EXECUTE format('CREATE ROLE %I', name);
        END IF;
        EXECUTE format('ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT', name);
    END LOOP;
    -- Refuse inherited authority outside the declared contract, including ADMIN OPTION.
    IF EXISTS (
        SELECT FROM pg_auth_members m
        JOIN pg_roles member ON member.oid = m.member
        JOIN pg_roles parent ON parent.oid = m.roleid
        WHERE member.rolname IN ('fred_cp', 'fred_kf', 'fred_runtime', 'fred_monitor',
            'fred_kf_reader', 'fred_runtime_reader', 'fred_monitor_reader')
        AND (m.admin_option OR (member.rolname, parent.rolname) NOT IN (
            ('fred_kf', 'fred_kf_reader'), ('fred_runtime', 'fred_runtime_reader'),
            ('fred_monitor', 'fred_monitor_reader')))
    ) THEN
        RAISE EXCEPTION 'unexpected Fred role membership; review it before bootstrap';
    END IF;
END
$bootstrap$;
ALTER ROLE fred_cp LOGIN;
ALTER ROLE fred_kf LOGIN;
ALTER ROLE fred_runtime LOGIN;
ALTER ROLE fred_monitor LOGIN CONNECTION LIMIT 4;
ALTER ROLE fred_kf_reader NOLOGIN;
ALTER ROLE fred_runtime_reader NOLOGIN;
ALTER ROLE fred_monitor_reader NOLOGIN;
GRANT fred_kf_reader TO fred_kf;
GRANT fred_runtime_reader TO fred_runtime;
GRANT fred_monitor_reader TO fred_monitor;
CREATE SCHEMA IF NOT EXISTS control_plane AUTHORIZATION fred_cp;
CREATE SCHEMA IF NOT EXISTS cp_read AUTHORIZATION fred_cp;
CREATE SCHEMA IF NOT EXISTS runtime AUTHORIZATION fred_runtime;
CREATE SCHEMA IF NOT EXISTS knowledge AUTHORIZATION fred_kf;
ALTER SCHEMA control_plane OWNER TO fred_cp;
ALTER SCHEMA cp_read OWNER TO fred_cp;
ALTER SCHEMA runtime OWNER TO fred_runtime;
ALTER SCHEMA knowledge OWNER TO fred_kf;
REVOKE ALL ON SCHEMA public FROM PUBLIC, fred_cp, fred_kf, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
REVOKE ALL ON DATABASE :"database" FROM PUBLIC, fred_cp, fred_kf, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
GRANT CONNECT ON DATABASE :"database" TO fred_cp, fred_kf, fred_runtime, fred_monitor;
REVOKE ALL ON SCHEMA control_plane FROM PUBLIC, fred_kf, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
REVOKE ALL ON SCHEMA cp_read FROM PUBLIC, fred_kf, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
REVOKE ALL ON SCHEMA runtime FROM PUBLIC, fred_cp, fred_kf, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
REVOKE ALL ON SCHEMA knowledge FROM PUBLIC, fred_cp, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
GRANT USAGE ON SCHEMA cp_read TO fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
-- Cross-schema FKs bind runtime payloads to the CP conversation root.
-- Table REFERENCES is granted by CP migration 0009; no SELECT/DML is granted.
GRANT USAGE ON SCHEMA control_plane TO fred_runtime;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA knowledge;
DO $bootstrap$
BEGIN
    IF EXISTS (SELECT FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
               WHERE e.extname = 'vector' AND n.nspname <> 'knowledge') THEN
        RAISE EXCEPTION 'vector must be in knowledge; recreate the Weaver database';
    END IF;
END
$bootstrap$;
ALTER ROLE fred_cp IN DATABASE :"database" SET search_path = control_plane;
ALTER ROLE fred_kf IN DATABASE :"database" SET search_path = knowledge;
ALTER ROLE fred_runtime IN DATABASE :"database" SET search_path = runtime;
ALTER ROLE fred_monitor IN DATABASE :"database" SET search_path = cp_read;
ALTER ROLE fred_monitor SET default_transaction_read_only = on;
COMMIT;
