-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE deletion DROP CONSTRAINT space_deletion_check2;
ALTER TABLE deletion ALTER COLUMN target_kind TYPE text USING target_kind::text;
ALTER TABLE deletion ADD CONSTRAINT deletion_target_kind_check
    CHECK (target_kind IN ('organization', 'team', 'project', 'document'));
ALTER TABLE deletion ADD CONSTRAINT deletion_target_parent_check
    CHECK ((target_kind = 'organization') = (target_parent_id IS NULL));
