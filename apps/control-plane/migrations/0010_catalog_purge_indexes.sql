-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Placement lookups and foreign-key checks must include retired documents.
create index document_space_folder on document (space_id, folder_id);

-- Purge selects each space's folders in ID order, including retired rows.
create index folder_space on folder (space_id, id);

-- Leaf detection looks up children by parent alone, regardless of deletion state.
create index folder_parent on folder (parent_id) where parent_id is not null;
