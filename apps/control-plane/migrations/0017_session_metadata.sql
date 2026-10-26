-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Product index only. Runtime owns messages/checkpoints. Immutable identifiers
-- deliberately have no cascading FK: retirement/purge must not erase provenance.
CREATE TABLE session_metadata (
    session_id text PRIMARY KEY,
    user_id text NOT NULL,
    space_id uuid NOT NULL,
    agent_instance_id uuid NOT NULL,
    template_id uuid NOT NULL,
    runtime_id text NOT NULL,
    agent_display_name varchar(255) NOT NULL,
    title varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (session_id ~ '^[A-Za-z0-9_-]{1,128}$')
);

CREATE INDEX session_metadata_owner_activity
    ON session_metadata (space_id, user_id, updated_at DESC, session_id);
