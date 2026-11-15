-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Fresh Weaver initialization only. NULL inherits the existing lifecycle policy;
-- zero requests immediate eligibility for the existing durable purge worker.
ALTER TABLE space ADD COLUMN conversation_retention_seconds bigint;
ALTER TABLE space ADD CONSTRAINT team_conversation_retention CHECK (
    conversation_retention_seconds IS NULL OR
    (kind = 'team' AND conversation_retention_seconds >= 0)
);
