-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Add document-tree display columns without rewriting the deployed cp_read history.
-- Append columns: CREATE OR REPLACE preserves existing column positions and SELECT grants.
-- SQLx runs this file and its history entry in one transaction.
set local lock_timeout = '5s';

create or replace view cp_read.document_visibility as
select d.id as document_id, d.space_id, d.folder_id,
       d.session_id as conversation_id, sm.user_id as conversation_owner,
       g.id as generation_id, g.vector_ordinals,
       d.name, d.sha256 as source_revision,
       cardinality(f.rejection_reasons) = 0 as visible,
       f.rejection_reasons, d.mime, d.created_at
from document d
join space s on s.id = d.space_id
left join session_metadata sm on sm.session_id = d.session_id and sm.space_id = d.space_id
left join generation g on g.id = d.published_generation
cross join lateral (
    select array_remove(array[
        case when d.deletion_id is not null then 'document_deleted' end,
        case when s.deletion_id is not null then 'space_deleted' end,
        case when not d.retrievable then 'not_retrievable' end,
        case when d.retrievable_pending is distinct from false then 'retrievable_pending' end,
        case when g.id is null then 'not_published' end,
        case when d.session_id is not null and
            (sm.session_id is null or sm.deletion_id is not null) then 'conversation_unavailable' end
    ]::text[], null) as rejection_reasons
) f;

create or replace view cp_read.space_state as
select id, deletion_id is not null as retired, name from space;

create or replace view cp_read.folder_path as
select id, space_id, path, name from folder where deletion_id is null;
