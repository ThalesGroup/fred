-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE agent_instance
    ADD COLUMN configuration_revision bigint NOT NULL DEFAULT 1 CHECK (configuration_revision > 0);
ALTER TABLE session_metadata
    ADD COLUMN agent_configuration_revision bigint NOT NULL DEFAULT 1 CHECK (agent_configuration_revision > 0);
ALTER TABLE session_metadata ALTER COLUMN agent_configuration_revision DROP DEFAULT;
