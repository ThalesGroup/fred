-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Retired folders and documents are absent from reads and name uniqueness.
ALTER TABLE folder ADD COLUMN deletion_id uuid REFERENCES deletion (id);
ALTER TABLE document ADD COLUMN deletion_id uuid REFERENCES deletion (id);
CREATE INDEX folder_deletion_manifest ON folder (deletion_id) WHERE deletion_id IS NOT NULL;
CREATE INDEX document_deletion_manifest ON document (deletion_id) WHERE deletion_id IS NOT NULL;
ALTER TABLE folder DROP CONSTRAINT folder_space_id_parent_id_name_key;
CREATE UNIQUE INDEX folder_space_id_parent_id_name_key ON folder (space_id, parent_id, name)
    NULLS NOT DISTINCT WHERE deletion_id IS NULL;
ALTER TABLE document DROP CONSTRAINT document_space_id_folder_id_name_key;
CREATE UNIQUE INDEX document_space_id_folder_id_name_key ON document (space_id, folder_id, name)
    NULLS NOT DISTINCT WHERE deletion_id IS NULL;
