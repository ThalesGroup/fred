-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Configured instances are space-owned data; executable templates stay in the runtime.
CREATE TABLE agent_instance (
    agent_instance_id uuid PRIMARY KEY,
    space_id uuid NOT NULL REFERENCES space (id),
    template_id uuid NOT NULL,
    source_runtime_id text NOT NULL,
    source_agent_id text NOT NULL,
    display_name varchar(255) NOT NULL,
    description varchar(500),
    enabled boolean NOT NULL DEFAULT true,
    created_by text,
    updated_by text,
    tuning jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Names are trimmed on write, as in Swift; the index arbitrates concurrent creates.
CREATE UNIQUE INDEX uq_agent_instance_space_name ON agent_instance (space_id, lower(display_name));
-- No cascade: space purge must explicitly resolve instance retention/removal first.
