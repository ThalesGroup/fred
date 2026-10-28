-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Session IDs are UUIDs, so a conversation is an ordinary deletion target.
-- They are client-chosen: a target is identified by its kind and its ID.
ALTER TABLE deletion DROP CONSTRAINT deletion_target_id_key;
ALTER TABLE deletion ADD CONSTRAINT deletion_target_key UNIQUE (target_kind, target_id);
ALTER TABLE session_metadata DROP CONSTRAINT session_metadata_session_id_check;
ALTER TABLE session_metadata ALTER COLUMN session_id TYPE uuid USING session_id::uuid;
ALTER TABLE session_metadata ADD COLUMN deletion_id uuid REFERENCES deletion (id);
ALTER TABLE deletion DROP CONSTRAINT deletion_target_kind_check;
ALTER TABLE deletion ADD CONSTRAINT deletion_target_kind_check
    CHECK (target_kind IN ('organization', 'team', 'project', 'document', 'session'));
