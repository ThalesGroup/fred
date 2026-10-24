-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- SQLx runs this conversion transactionally; the lock excludes concurrent writes.
LOCK TABLE space IN ACCESS EXCLUSIVE MODE;
ALTER TABLE space DROP CONSTRAINT space_check;
ALTER TABLE space DISABLE TRIGGER space_immutable;
UPDATE space SET kind = 'personal' WHERE personal_owner IS NOT NULL;
ALTER TABLE space ENABLE TRIGGER space_immutable;
ALTER TABLE space ADD CONSTRAINT space_personal_identity CHECK (
    (kind = 'personal') = (personal_owner IS NOT NULL)
    AND (kind <> 'personal' OR parent_id IS NULL)
);
COMMENT ON COLUMN space.personal_owner IS 'Owner identity of a personal space; null for other space kinds';
