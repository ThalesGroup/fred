-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Bootstrap creates owners and reader groups before SQLx runs as fred_cp.
-- Views use the owner's privileges; consumers receive SELECT only, never base-table access.

create view cp_read.document_visibility as
select d.id as document_id, d.space_id, d.folder_id,
       d.session_id as conversation_id, sm.user_id as conversation_owner,
       g.id as generation_id, g.vector_ordinals,
       d.name, d.mime, d.created_at, d.sha256 as source_revision,
       cardinality(f.rejection_reasons) = 0 as visible,
       f.rejection_reasons
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
-- document_id identifies candidates; space/folder/conversation facts constrain the request.
-- conversation_owner binds attachments to the person; generation_id/vector_ordinals fence chunks.
-- mime/created_at supply document-tree media type and arrival time without artifact reads.
-- name/source_revision are the existing tabular result fields. visible is the sole lifecycle
-- and publication predicate. rejection_reasons preserves aggregate diagnostics without Python policy.

create view cp_read.published_artifact as
select d.id as document_id, a.path, a.size, a.sha256, g.prefix
from document d
join generation g on g.id = d.published_generation
join artifact a on a.generation_id = g.id;
-- document_id/path select the requested published artifact; prefix locates it, size/sha256 verify it.

create view cp_read.space_state as
select id, name, deletion_id is not null as retired from space;
-- name labels document-tree spaces. id resolves the anchor; retired preserves the distinct missing/pending-deletion API errors.
create view cp_read.folder_path as
select id, space_id, path, name from folder where deletion_id is null;
-- name labels document-tree folders; path also supplies their parent IDs.
-- id/space_id enforce folder selection within the authorized corpus; path prefilters vector hits.
create view cp_read.conversation as
select session_id as conversation_id, space_id, user_id as owner
from session_metadata where deletion_id is null;
-- All three facts are needed to bind an explicit attachment list to its live conversation/person.

create view cp_read.terms_acceptance as select user_id, version from terms_acceptance;
-- Runtime checks the effective person's acceptance of the configured terms version.
create view cp_read.platform_role_grant as select subject, role from platform_role_grant;
-- Monitor's existing SDK resolves platform roles for the authenticated subject.

revoke all on all tables in schema cp_read from public, fred_kf, fred_runtime, fred_monitor,
    fred_kf_reader, fred_runtime_reader, fred_monitor_reader;
grant select on cp_read.document_visibility, cp_read.published_artifact,
    cp_read.space_state, cp_read.folder_path, cp_read.conversation to fred_kf_reader;
grant select on cp_read.terms_acceptance to fred_runtime_reader;
grant select on cp_read.platform_role_grant to fred_monitor_reader;
