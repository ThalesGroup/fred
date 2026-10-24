-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE space_deletion RENAME TO deletion;
ALTER INDEX space_deletion_due RENAME TO deletion_due;
ALTER INDEX space_deletion_overlap RENAME TO deletion_overlap;
ALTER TABLE deletion RENAME CONSTRAINT space_deletion_pkey TO deletion_pkey;
ALTER TABLE deletion RENAME CONSTRAINT space_deletion_target_id_key TO deletion_target_id_key;
