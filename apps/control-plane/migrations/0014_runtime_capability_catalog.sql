-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Observations of logical pods, not deployment replicas or execution readiness.
CREATE TABLE runtime_catalog (
    runtime_id text PRIMARY KEY CHECK (runtime_id <> '' AND runtime_id = btrim(runtime_id)),
    reachable boolean NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    observed_at timestamptz
);

CREATE TABLE runtime_capability (
    runtime_id text NOT NULL REFERENCES runtime_catalog (runtime_id),
    capability_id text NOT NULL CHECK (capability_id <> '' AND capability_id = btrim(capability_id)),
    version text NOT NULL CHECK (version <> '' AND version = btrim(version)),
    descriptor jsonb NOT NULL CHECK (jsonb_typeof(descriptor) = 'object'),
    advertised boolean NOT NULL,
    PRIMARY KEY (runtime_id, capability_id)
);

-- A single runtime key binds both the template and its capability offering.
CREATE TABLE runtime_template_capability (
    runtime_id text NOT NULL,
    source_agent_id text NOT NULL CHECK (source_agent_id <> '' AND source_agent_id = btrim(source_agent_id)),
    capability_id text NOT NULL,
    default_selected boolean NOT NULL,
    PRIMARY KEY (runtime_id, source_agent_id, capability_id),
    FOREIGN KEY (runtime_id, capability_id)
        REFERENCES runtime_capability (runtime_id, capability_id)
);
