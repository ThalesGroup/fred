-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Folder names already exclude retired rows from uniqueness. Receipts retain
-- the old UUID after purge; recreating a name always creates a different target.
alter table deletion drop constraint deletion_target_kind_check;
alter table deletion add constraint deletion_target_kind_check
    check (target_kind in ('organization', 'team', 'project', 'document', 'session', 'folder'));

-- Purge also waits for failed uploads with uncertain writes or uncleaned objects;
-- the live-name index excludes them. Folder and document indexes already exist.
create index document_upload_folder on document_upload (folder_id) where folder_id is not null;
