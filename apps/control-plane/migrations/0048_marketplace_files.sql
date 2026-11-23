-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Marketplace configuration originals use the existing document catalogue and
-- upload journal. Their owning proposal holds one template in the current scope.
set local lock_timeout = '5s';

alter table marketplace_proposal add column document_id uuid references document(id) on delete set null;
create unique index marketplace_proposal_document on marketplace_proposal(document_id) where document_id is not null;

alter table document drop constraint document_purpose;
alter table document add constraint document_purpose check (purpose in ('source','output','wiki','marketplace'));
alter table document drop constraint document_wiki_placement;
alter table document add constraint document_copy_placement
    check (purpose not in ('wiki','marketplace') or (session_id is null and folder_id is null));
drop index document_active_path;
create unique index document_active_path on document (space_id, folder_id, session_id, purpose, parent_path, name)
    nulls not distinct where deletion_id is null and purpose in ('source','output')
    and (current_content_id is not null or purpose = 'output');
drop index document_wiki_retired;
create index document_copy_retired on document (id)
    where purpose in ('wiki','marketplace') and current_content_id is null and deletion_id is null;

alter table document_upload drop constraint document_upload_purpose;
alter table document_upload add constraint document_upload_purpose check (purpose in ('source','output','preview','wiki','marketplace'));
alter table document_upload drop constraint document_upload_request_fingerprint;
alter table document_upload add constraint document_upload_request_fingerprint check (
    (purpose in ('wiki','marketplace')) = (request_fingerprint is not null)
    and (request_fingerprint is null or request_fingerprint ~ '^[0-9a-f]{64}$'));
alter table document_upload drop constraint document_upload_placement;
alter table document_upload add constraint document_upload_placement check (
    (purpose = 'source' and (folder_id is null) = (session_id is not null))
    or (purpose in ('output','preview') and folder_id is null and session_id is not null)
    or (purpose in ('wiki','marketplace','preview') and folder_id is null and session_id is null));

create or replace function require_upload_placement() returns trigger language plpgsql as $$
begin
    if new.target_document_id is not null and not exists(select 1 from document d
        where d.id = new.target_document_id and d.space_id = new.space_id
        and d.folder_id is not distinct from new.folder_id and d.session_id is not distinct from new.session_id
        and d.purpose = case when new.purpose = 'preview'
            then case when new.session_id is null then 'wiki' else 'output' end else new.purpose end) then
        raise exception 'file write must belong to its declared destination' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

drop trigger wiki_copy_frozen on document;
alter function forbid_wiki_copy_change() rename to forbid_document_copy_change;
create or replace function forbid_document_copy_change() returns trigger language plpgsql as $$
begin
    if new.current_content_id is null and (old.purpose = 'wiki'
        or not exists(select 1 from marketplace_proposal where document_id=old.id and package is not null)) then
        return new;
    end if;
    raise exception 'a published copy is frozen' using errcode = '23514',
        constraint = TG_NAME, table = TG_TABLE_NAME;
end $$;
create trigger document_copy_frozen before update of current_content_id on document for each row
    when (old.purpose in ('wiki','marketplace') and old.current_content_id is not null
        and new.current_content_id is distinct from old.current_content_id)
    execute function forbid_document_copy_change();

-- No document authority is hidden in JSON. The FK remains until physical cleanup,
-- which detaches its terminal receipt; a live package can never lose its original.
create function protect_marketplace_document() returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' and new.document_id is distinct from old.document_id and
        (new.document_id is not null or exists(select 1 from document where id = old.document_id)) then
        raise exception 'only cleanup detaches a marketplace original' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.package is not null then
        if jsonb_path_exists(new.package, '$.content.capabilities.*.files.*') <> (new.document_id is not null)
            or (new.document_id is not null and not exists (
                select 1 from document d join document_content c on c.id = d.current_content_id
                join document_upload u on u.id = d.id
                where d.id = new.document_id and d.space_id = new.marketplace_space_id
                and d.purpose = 'marketplace' and d.deletion_id is null
                and c.cleaned_at is null and c.published_at is not null
                and u.purpose = 'marketplace' and u.status = 'stored' and not u.put_pending
                and u.target_document_id = d.id and u.content_id = c.id
                and (u.size,u.sha256,u.mime,u.object_key) = (c.size,c.sha256,c.mime,c.object_key)
                and (select count(*) from jsonb_path_query(new.package, '$.content.capabilities.*.files.*')) = 1
                and exists (select 1 from jsonb_path_query(new.package, '$.content.capabilities.*.files.*') f(value)
                    where f.value->>'document_id' = d.id::text and f.value->>'name' = d.name
                    and f.value->>'mime' = c.mime and f.value->>'size' = c.size::text and f.value->>'sha256' = c.sha256)
            )) then
            raise exception 'a marketplace package owns its verified organization original' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;
create trigger marketplace_proposal_document before insert or update on marketplace_proposal
    for each row execute function protect_marketplace_document();

create function retire_marketplace_document() returns trigger language plpgsql as $$
begin
    update document set current_content_id = null, updated_at = clock_timestamp()
        where id = old.document_id and deletion_id is null;
    return null;
end $$;
create trigger marketplace_document_retirement after update on marketplace_proposal
    for each row when (old.document_id is not null and old.package is not null and new.package is null)
    execute function retire_marketplace_document();
create trigger marketplace_document_deletion after delete on marketplace_proposal
    for each row when (old.document_id is not null) execute function retire_marketplace_document();

comment on trigger marketplace_proposal_document on marketplace_proposal is
    'assertion: consistency - marketplace file descriptors refer to a verified immutable copy in the catalogue organization';
comment on trigger document_upload_request_immutable on document_upload is
    'assertion: immutability - Wiki and marketplace copy request identity survives proposal deletion';
comment on trigger marketplace_document_retirement on marketplace_proposal is
    'effect: retire the original and release quota when its proposal payload is erased';
comment on trigger marketplace_document_deletion on marketplace_proposal is
    'effect: retire the original when its owning proposal is deleted';
comment on trigger document_copy_frozen on document is
    'assertion: immutability - published Wiki and marketplace copies keep their bytes until retirement';
