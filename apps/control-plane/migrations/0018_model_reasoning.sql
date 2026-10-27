-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE organization_model_permission
    ADD COLUMN reasoning_enabled boolean NOT NULL DEFAULT false;
