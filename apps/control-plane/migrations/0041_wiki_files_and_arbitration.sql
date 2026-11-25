-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh installations only. One arbitration for Wiki pages and files: a proposal is a
-- draft while bound to its conversation, then pending; acceptance publishes it, refusal
-- deletes it. A file revision owns one purpose='wiki' document (id = revision_id).
-- Obligations of Control Plane: Drive readers filter purpose='source'; space retirement
-- marks Wiki copies; the content sweep cleans a document whose current content is null.
set local lock_timeout = '5s';

-- One owner of sibling-name normalization: this index and Control Plane queries.
create function wiki_title_key(title text) returns text language sql immutable strict parallel safe
    return lower(btrim(regexp_replace(title, '[[:space:]]+', ' ', 'g')));

-- Tree: typed references replace untyped (page_id, space_id) ones -------------------
alter table wiki_page drop constraint wiki_page_parent_page_id_space_id_fkey;
alter table wiki_revision drop constraint wiki_revision_page_id_space_id_fkey;
alter table wiki_revision drop constraint wiki_revision_proposed_parent_page_id_space_id_fkey;
alter table wiki_page drop constraint wiki_page_page_id_space_id_key;

-- The review mark is replaced by arbitration.
alter table wiki_page drop column needs_review;
alter table wiki_page drop constraint wiki_page_kind_check;
alter table wiki_page add constraint wiki_page_kind check (kind in ('page','rules','file'));
-- A file entry exists only through an accepted revision.
alter table wiki_page add constraint wiki_file_current check (kind <> 'file' or current_revision_id is not null);
alter table wiki_page add constraint wiki_page_typed unique (page_id, space_id, kind);
-- Only a page has children: never the rules page, never a file.
alter table wiki_page add column parent_kind text generated always as ('page') stored;
alter table wiki_page add constraint wiki_page_parent foreign key (parent_page_id, space_id, parent_kind)
    references wiki_page (page_id, space_id, kind);
drop index wiki_sibling_title;
create unique index wiki_sibling_title on wiki_page (space_id, parent_page_id, wiki_title_key(title)) nulls not distinct;

-- Revisions and proposals -----------------------------------------------------------
-- author_kind duplicated agent_instance_id; expiry is replaced by arbitration (D10, D13).
alter table wiki_revision drop constraint wiki_revision_check;
alter table wiki_revision drop constraint wiki_revision_check1;
alter table wiki_revision drop constraint wiki_revision_check2;
alter table wiki_revision drop constraint wiki_revision_status_check;
alter table wiki_revision drop column author_kind;
alter table wiki_revision drop column expires_at;
drop index wiki_private_session;
-- The entry kind a revision belongs to, or would create; files carry no text.
alter table wiki_revision add column entry_kind text not null;
alter table wiki_revision add column document_id uuid;
-- Snapshot of the agent's name in its conversation; no foreign key: it outlives both.
alter table wiki_revision add column agent_name varchar(255);
alter table wiki_revision add column proposed_parent_kind text generated always as ('page') stored;
alter table wiki_revision add constraint wiki_revision_status check (status in ('proposed','published','superseded'));
alter table wiki_revision add constraint wiki_revision_entry check (
    entry_kind in ('page','rules','file')
    and (entry_kind = 'file') = (document_id is not null)
    and (document_id is null or (document_id = revision_id and content_md = '')));
alter table wiki_revision add constraint wiki_revision_shape check (
    -- A decided revision belongs to an entry and to no conversation.
    (status = 'proposed' or page_id is not null)
    and (status = 'proposed' or session_id is null)
    and (status <> 'proposed' or reviewed_at is null)
    -- A new entry is named; an edit names the revision it was made on.
    and (status <> 'proposed' or page_id is not null or proposed_title is not null)
    and (status <> 'proposed' or page_id is null or base_revision_id is not null)
    and (proposed_parent_page_id is null or proposed_title is not null)
    -- Nobody proposes rules; files keep only their current version (D19).
    and (entry_kind <> 'rules' or status <> 'proposed')
    and (entry_kind <> 'file' or status <> 'superseded')
    -- Drafts are agents'; agent provenance is a pair.
    and (session_id is null or agent_instance_id is not null)
    and ((agent_instance_id is null) = (agent_name is null)));
-- Deleting an entry deletes its revisions and its pending proposals (D21).
alter table wiki_revision add constraint wiki_revision_page foreign key (page_id, space_id, entry_kind)
    references wiki_page (page_id, space_id, kind) on delete cascade;
-- Deleting a page deletes the proposals that would create an entry under it (D21).
alter table wiki_revision add constraint wiki_revision_proposed_parent
    foreign key (proposed_parent_page_id, space_id, proposed_parent_kind)
    references wiki_page (page_id, space_id, kind) on delete cascade;
-- A file revision keeps its bytes; the document is retired after the revision goes.
alter table wiki_revision add constraint wiki_revision_document foreign key (document_id) references document (id);
-- A draft belongs to its owner's conversation in the same space and is purged with it.
alter table wiki_revision add constraint wiki_revision_draft foreign key (session_id, space_id)
    references session_metadata (session_id, space_id) on delete cascade;
create index wiki_pending on wiki_revision (space_id, created_at desc, revision_id desc)
    where status = 'proposed' and session_id is null;
create index wiki_draft_session on wiki_revision (session_id, space_id) where session_id is not null;
create index wiki_proposed_parent on wiki_revision (proposed_parent_page_id) where proposed_parent_page_id is not null;
create index wiki_revision_document on wiki_revision (document_id) where document_id is not null;

create or replace function protect_wiki_revision() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        -- Agent provenance and file bytes come only from a conversation: such a proposal,
        -- even a person's own, is born a draft and a person's own is detached at once.
        if new.session_id is null and (new.agent_instance_id is not null or new.document_id is not null) then
            raise exception 'agent provenance and Wiki files come from a conversation' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        -- A draft carries its live conversation's owner and agent, as the person saw it.
        if new.session_id is not null and not exists(select 1 from session_metadata m
            where m.session_id = new.session_id and m.space_id = new.space_id
            and m.user_id = new.author_user_id and m.deletion_id is null
            and m.agent_instance_id = new.agent_instance_id and m.agent_display_name = new.agent_name) then
            raise exception 'a draft belongs to its author''s live conversation' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        -- A file revision owns one live Wiki copy of the same space, holding exactly the
        -- current bytes of an output of its conversation.
        if new.document_id is not null and not exists(select 1 from document d
            join document_content c on c.id = d.current_content_id
            join document o on o.session_id = new.session_id and o.space_id = d.space_id
                and o.purpose = 'output' and o.deletion_id is null
            join document_content oc on oc.id = o.current_content_id
            where d.id = new.document_id and d.space_id = new.space_id and d.purpose = 'wiki'
            and d.deletion_id is null and (oc.size, oc.sha256, oc.mime) = (c.size, c.sha256, c.mime)) then
            raise exception 'a file revision owns a live Wiki copy of its conversation''s output' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        return new;
    end if;
    if (new.revision_id, new.space_id, new.entry_kind, new.content_md, new.document_id,
        new.author_user_id, new.agent_instance_id, new.agent_name, new.created_at,
        new.base_revision_id, new.proposed_title, new.proposed_parent_page_id)
       is distinct from
       (old.revision_id, old.space_id, old.entry_kind, old.content_md, old.document_id,
        old.author_user_id, old.agent_instance_id, old.agent_name, old.created_at,
        old.base_revision_id, old.proposed_title, old.proposed_parent_page_id)
       or (old.page_id is not null and new.page_id is distinct from old.page_id)
       -- Confirmation only detaches a draft from its conversation.
       or (new.session_id is distinct from old.session_id and new.session_id is not null)
       or ((new.reviewed_at, new.reviewed_by) is distinct from (old.reviewed_at, old.reviewed_by)
           and old.status <> 'proposed')
       or (new.status <> old.status and not
           ((old.status = 'proposed' and new.status = 'published')
             or (old.status = 'published' and new.status = 'superseded'))) then
        raise exception 'wiki revision content and provenance are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
drop trigger wiki_revision_immutable on wiki_revision;
create trigger wiki_revision_immutable before insert or update on wiki_revision
    for each row execute function protect_wiki_revision();

-- Whatever removes a file revision (refusal, withdrawal, replacement, entry or page
-- deletion, conversation purge of a draft) releases its quota and schedules its bytes.
-- A retired space's documents are already marked and keep their own purge.
create function retire_wiki_copy() returns trigger language plpgsql as $$
begin
    update document set current_content_id = null, updated_at = clock_timestamp()
        where id = old.document_id and deletion_id is null;
    return null;
end $$;
create trigger wiki_copy_retirement after delete on wiki_revision
    for each row when (old.document_id is not null) execute function retire_wiki_copy();

-- Document catalogue: a third, destination-less purpose ------------------------------
alter table document drop constraint document_purpose_check;
alter table document add constraint document_purpose check (purpose in ('source','output','wiki'));
alter table document add constraint document_wiki_placement check (purpose <> 'wiki' or (session_id is null and folder_id is null));
-- Wiki names are unique in the Wiki tree (wiki_sibling_title), not in the catalogue.
drop index document_active_path;
create unique index document_active_path on document (space_id, folder_id, session_id, purpose, parent_path, name)
    nulls not distinct where deletion_id is null and purpose <> 'wiki'
    and (current_content_id is not null or purpose = 'output');
-- Bounded sweep of retired copies once their contents and receipts are gone.
create index document_wiki_retired on document (id)
    where purpose = 'wiki' and current_content_id is null and deletion_id is null;

alter table document_upload drop constraint document_upload_purpose_check;
alter table document_upload add constraint document_upload_purpose check (purpose in ('source','output','preview','wiki'));
alter table document_upload drop constraint document_upload_check1;
-- A Drive or attachment source names one destination; an output or its preview names its
-- conversation; a Wiki copy or its preview names neither.
alter table document_upload add constraint document_upload_placement check (
    (purpose = 'source' and (folder_id is null) = (session_id is not null))
    or (purpose in ('output','preview') and folder_id is null and session_id is not null)
    or (purpose in ('wiki','preview') and folder_id is null and session_id is null));
drop index document_upload_active_name;
create unique index document_upload_active_name on document_upload (space_id, folder_id, session_id, purpose, parent_path, name)
    nulls not distinct where status = 'pending' and (folder_id is not null or session_id is not null);

create or replace function require_upload_placement() returns trigger language plpgsql as $$
begin
    if new.target_document_id is not null and not exists(select 1 from document d
        where d.id = new.target_document_id and d.space_id = new.space_id
        and d.folder_id is not distinct from new.folder_id and d.session_id is not distinct from new.session_id
        and d.purpose = case when new.purpose = 'source' then 'source'
            when new.session_id is null then 'wiki' else 'output' end) then
        raise exception 'file write must belong to its declared destination' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

-- A published Wiki copy is frozen (D14): it can only be retired.
create function forbid_wiki_copy_change() returns trigger language plpgsql as $$
begin
    raise exception 'a Wiki copy is frozen' using errcode = '23514',
        constraint = TG_NAME, table = TG_TABLE_NAME;
end $$;
create trigger wiki_copy_frozen before update of current_content_id on document for each row
    when (old.purpose = 'wiki' and old.current_content_id is not null
        and new.current_content_id is not null and new.current_content_id <> old.current_content_id)
    execute function forbid_wiki_copy_change();

-- Its owner can no longer reach a deleted conversation's drafts: they go at once and
-- release their copies' quota, before the conversation's purge.
create function retire_conversation_drafts() returns trigger language plpgsql as $$
begin
    delete from wiki_revision where session_id = new.session_id;
    return null;
end $$;
create trigger session_drafts_retirement after update of deletion_id on session_metadata
    for each row when (old.deletion_id is null and new.deletion_id is not null)
    execute function retire_conversation_drafts();

comment on trigger wiki_copy_frozen on document is
    'assertion: immutability - a published Wiki copy keeps its content until retired';
comment on trigger session_drafts_retirement on session_metadata is
    'effect: delete the Wiki drafts of a conversation marked for deletion';
comment on trigger wiki_revision_immutable on wiki_revision is
    'assertion: immutability - wiki revision content and provenance; conversation provenance only through a draft of its owner''s live conversation; file revisions copy one of its outputs';
comment on trigger wiki_copy_retirement on wiki_revision is
    'effect: retire the Wiki copy of a removed file revision';
