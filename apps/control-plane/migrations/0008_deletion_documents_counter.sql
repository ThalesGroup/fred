-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE deletion ADD COLUMN documents_deleted bigint NOT NULL DEFAULT 0
    CHECK (documents_deleted >= 0);
