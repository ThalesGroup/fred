-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh initialization only. Keep the privacy boundary after physical document
-- purge: target_parent_id alone cannot distinguish a drive file from an attachment.
alter table deletion add column document_session_id uuid;
alter table deletion add constraint deletion_document_session_kind
    check (document_session_id is null or target_kind = 'document');

-- Activity reads include acknowledged and terminal receipts, unlike the worker
-- and personal inbox indexes. No new task or history store is introduced.
create index document_upload_team_activity
    on document_upload(space_id, created_at desc, id desc) where session_id is null;
create index deletion_team_activity
    on deletion(organization_id, target_parent_id, requested_at desc, id desc)
    where target_kind in ('document','folder') and document_session_id is null;
create index document_processing_activity on document_processing(created_at desc, id desc);
