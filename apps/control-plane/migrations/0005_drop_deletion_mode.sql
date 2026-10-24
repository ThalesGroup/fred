-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Zero retention expresses immediate deletion.
ALTER TABLE space_deletion DROP COLUMN mode;
