-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh installations only. File identity is independent of immutable bytes.
set local lock_timeout = '5s';
do $$ begin
    if exists(select 1 from document) or exists(select 1 from document_upload)
        or exists(select 1 from powerpoint_file)
        or exists(select 1 from storage_budget where used_bytes<>0 or reserved_bytes<>0) then
        raise exception 'conversation file catalogue requires a fresh installation';
    end if;
end $$;

drop view cp_read.document_visibility;
drop view cp_read.published_artifact;
alter table document drop column mime, drop column size, drop column sha256, drop column object_key;
alter table document add column purpose text not null default 'source'
    check (purpose in ('source','output'));
alter table document add column parent_path text not null default '';
alter table document add column current_content_id uuid;
alter table document add column updated_at timestamptz not null default now();
alter table document add constraint document_output_placement check
    (purpose <> 'output' or (session_id is not null and folder_id is null));
alter table document add constraint document_parent_path check
    ((purpose = 'output' or parent_path = '') and octet_length(parent_path) <= 768
     and parent_path !~ '(^/|/$|//|(^|/)\.{1,2}(/|$)|[[:cntrl:]\\])');
drop index if exists document_space_id_folder_id_name_key;
create unique index document_active_path on document
    (space_id, folder_id, session_id, purpose, parent_path, name) nulls not distinct
    where deletion_id is null and (current_content_id is not null or purpose='output');
create index document_quota_owner on document(quota_owner);
create index document_outputs on document(session_id, updated_at desc, id desc)
    where purpose='output' and deletion_id is null and current_content_id is not null;

create table document_content (
    id uuid primary key,
    document_id uuid not null references document(id) on delete cascade,
    kind text not null check(kind in ('primary','preview')),
    source_content_id uuid,
    object_key text not null unique,
    mime text not null,
    size bigint not null check(size >= 0 and size <= 104857600),
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    published_at timestamptz,
    cleanup_after timestamptz,
    cleaned_at timestamptz,
    unique(id, document_id),
    foreign key(source_content_id, document_id) references document_content(id, document_id)
        deferrable initially deferred,
    check((kind='preview') = (source_content_id is not null)),
    check(source_content_id is distinct from id)
);
create index document_content_owner on document_content(document_id);
create index document_content_preview on document_content(source_content_id)
    where source_content_id is not null;
create unique index document_content_published_preview on document_content(source_content_id)
    where kind='preview' and published_at is not null and cleaned_at is null;
create index document_content_cleanup on document_content(cleanup_after,id) include(size) where cleaned_at is null and cleanup_after is not null;
alter table document add constraint document_current_content_fk
    foreign key(current_content_id,id) references document_content(id,document_id)
    deferrable initially deferred;

-- A single projection for readers; no writable compatibility view or mirrored metadata.
create view document_current as
select d.*, c.mime,c.size,c.sha256,c.object_key from document d
join document_content c on c.id=d.current_content_id and c.document_id=d.id
where d.current_content_id is not null;

alter table document_upload add column target_document_id uuid references document(id) on delete set null;
alter table document_upload add column content_id uuid references document_content(id) on delete set null;
alter table document_upload add column expected_content_id uuid;
alter table document_upload add column purpose text not null default 'source'
    check(purpose in ('source','output','preview'));
alter table document_upload add column parent_path text not null default '';
alter table document_upload add column reserved_bytes bigint not null default 0 check(reserved_bytes>=0);
create unique index document_upload_content on document_upload(content_id);
create unique index document_upload_writer on document_upload(target_document_id) where status='pending';
drop index document_upload_active_name;
create unique index document_upload_active_name on document_upload
    (space_id,folder_id,session_id,purpose,parent_path,name) nulls not distinct where status='pending';
create index document_upload_target on document_upload(target_document_id);

create function protect_document_content() returns trigger language plpgsql as $$
begin
    if (new.id,new.document_id,new.kind,new.source_content_id,new.object_key,new.mime,new.size,new.sha256)
        is distinct from (old.id,old.document_id,old.kind,old.source_content_id,old.object_key,old.mime,old.size,old.sha256)
        or (old.published_at is not null and new.published_at is distinct from old.published_at)
        or (old.cleaned_at is not null and new.cleaned_at is distinct from old.cleaned_at) then
        raise exception 'file content is immutable' using errcode='23514';
    end if;
    if new.cleaned_at is not null and exists(select 1 from document d where d.id=new.document_id
        and d.deletion_id is null and (d.current_content_id=new.id or d.current_content_id=new.source_content_id)) then
        raise exception 'current content cannot be cleaned' using errcode='23514';
    end if;
    return new;
end $$;
create trigger document_content_immutable before update on document_content
    for each row execute function protect_document_content();

create function protect_document_current() returns trigger language plpgsql as $$
begin
    if new.current_content_id is not null and new.deletion_id is null and not exists
        (select 1 from document_content c where c.id=new.current_content_id and c.document_id=new.id
         and c.kind='primary' and c.published_at is not null and c.cleaned_at is null) then
        raise exception 'current file content must be published and owned' using errcode='23514';
    end if;
    if tg_op='UPDATE' then
        if new.purpose is distinct from old.purpose or new.quota_owner is distinct from old.quota_owner or
            (old.purpose='source' and old.current_content_id is not null and new.deletion_id is null
             and new.current_content_id is distinct from old.current_content_id) then
            raise exception 'file purpose, quota owner and source content are immutable' using errcode='23514';
        end if;
    end if;
    return new;
end $$;
create trigger document_current_valid before insert or update on document
    for each row execute function protect_document_current();

create function protect_document_preview() returns trigger language plpgsql as $$
begin
    if new.kind='preview' and not exists(select 1 from document_content
        where id=new.source_content_id and document_id=new.document_id and kind='primary') then
        raise exception 'preview requires its own primary content' using errcode='23514';
    end if;
    return new;
end $$;
create trigger document_preview_valid before insert on document_content
    for each row execute function protect_document_preview();

-- Local and organization accounts overlap. Writers provision both before their
-- first reservation. Every producer, retirement and failure updates them here.
create function change_storage_budget(owner uuid, used_delta bigint, reserved_delta bigint)
returns void language plpgsql as $$
declare org uuid; account record;
begin
    if used_delta=0 and reserved_delta=0 then return; end if;
    select organization_id into strict org from space where id=owner;
    for account in select * from storage_budget
        where (space_id=org and scope='organization_total') or (space_id=owner and scope='local')
        order by (scope='organization_total') desc,space_id for update loop
        if (used_delta+reserved_delta>0) and
            account.used_bytes+account.reserved_bytes+used_delta+reserved_delta>account.limit_bytes then
            raise exception 'storage quota exceeded' using errcode='P0001';
        end if;
        update storage_budget set used_bytes=used_bytes+used_delta,reserved_bytes=reserved_bytes+reserved_delta
            where space_id=account.space_id and scope=account.scope;
    end loop;
    if (select count(*) from storage_budget where
        (space_id=org and scope='organization_total') or (space_id=owner and scope='local')) <> 2 then
        raise exception 'storage budgets must be initialized' using errcode='23514';
    end if;
end $$;

create function account_document() returns trigger language plpgsql as $$
declare before_bytes bigint:=0; after_bytes bigint:=0;
begin
    if tg_op<>'INSERT' and old.deletion_id is null then
        select coalesce((select size from document_content where id=old.current_content_id),0) into before_bytes;
    end if;
    if tg_op<>'DELETE' and new.deletion_id is null then
        select coalesce((select size from document_content where id=new.current_content_id),0) into after_bytes;
    end if;
    perform change_storage_budget(case when tg_op='DELETE' then old.quota_owner else new.quota_owner end,
        after_bytes-before_bytes,0);
    return case when tg_op='DELETE' then old else new end;
end $$;
create trigger document_account before insert or delete on document
    for each row execute function account_document();

create function account_document_upload() returns trigger language plpgsql as $$
declare before_bytes bigint:=0; after_bytes bigint:=0;
begin
    if tg_op<>'INSERT' and old.status='pending' then before_bytes:=old.reserved_bytes; end if;
    if tg_op<>'DELETE' and new.status='pending' then after_bytes:=new.reserved_bytes; end if;
    perform change_storage_budget(case when tg_op='DELETE' then old.quota_owner else new.quota_owner end,
        0,after_bytes-before_bytes);
    return null;
end $$;
create trigger document_upload_account after insert or update or delete on document_upload
    for each row execute function account_document_upload();

create function account_powerpoint_file() returns trigger language plpgsql as $$
declare bu bigint:=0; br bigint:=0; au bigint:=0; ar bigint:=0;
begin
    if tg_op<>'INSERT' then
        if old.status='pending' then br:=old.size; elsif old.status='stored' then bu:=old.size; end if;
    end if;
    if tg_op<>'DELETE' then
        if new.status='pending' then ar:=new.size; elsif new.status='stored' then au:=new.size; end if;
    end if;
    perform change_storage_budget(case when tg_op='DELETE' then old.quota_owner else new.quota_owner end,au-bu,ar-br);
    return null;
end $$;
create trigger powerpoint_file_account after insert or update or delete on powerpoint_file
    for each row execute function account_powerpoint_file();

create view cp_read.document_visibility as
select d.id as document_id,d.space_id,d.folder_id,d.session_id as conversation_id,sm.user_id as conversation_owner,
       g.id as generation_id,g.vector_ordinals,d.name,d.sha256 as source_revision,
       cardinality(f.rejection_reasons)=0 as visible,f.rejection_reasons,d.mime,d.created_at
from document_current d join space s on s.id=d.space_id
left join session_metadata sm on sm.session_id=d.session_id and sm.space_id=d.space_id
left join generation g on g.id=d.published_generation
cross join lateral (select array_remove(array[
    case when d.deletion_id is not null then 'document_deleted' end,
    case when s.deletion_id is not null then 'space_deleted' end,
    case when not d.retrievable or d.purpose<>'source' then 'not_retrievable' end,
    case when d.retrievable_pending is distinct from false then 'retrievable_pending' end,
    case when g.id is null then 'not_published' end,
    case when d.session_id is not null and (sm.session_id is null or sm.deletion_id is not null)
        then 'conversation_unavailable' end]::text[],null) as rejection_reasons) f;
create view cp_read.published_artifact as
select d.id as document_id,a.path,a.size,a.sha256,g.prefix from document d
join generation g on g.id=d.published_generation join artifact a on a.generation_id=g.id
where d.purpose='source';
grant select on cp_read.document_visibility,cp_read.published_artifact to fred_kf_reader;

-- Deliverables never enter KF implicitly, even through another application path.
alter table document add constraint output_not_indexed check
    (purpose='source' or (not retrievable and published_generation is null and retrieval_id is null));
create function require_processing_source() returns trigger language plpgsql as $$
begin
    if not exists(select 1 from document where id=new.document_id and purpose='source') then
        raise exception 'only source documents may be ingested' using errcode='23514';
    end if;
    return new;
end $$;
create trigger processing_source before insert or update of document_id on document_processing
    for each row execute function require_processing_source();
comment on table storage_budget is
    'Current primary file bytes and pending positive growth reservations, including PowerPoint configuration files. Previews and superseded contents are cleanup inventory, not user quota. Local and organization_total accounts overlap.';

-- Queue only obsolete bytes, making reclamation and backlog checks indexable.
create function retire_document_contents() returns trigger language plpgsql as $$
begin
    if new.deletion_id is distinct from old.deletion_id and new.deletion_id is not null then
        update document_content set cleanup_after=(select due_at from deletion where id=new.deletion_id)
            where document_id=new.id and cleaned_at is null;
    elsif new.current_content_id is distinct from old.current_content_id then
        update document_content set cleanup_after=clock_timestamp()
            where document_id=new.id and (id=old.current_content_id or source_content_id=old.current_content_id)
                and cleaned_at is null;
    end if;
    return null;
end $$;
create trigger document_contents_retirement after update of current_content_id,deletion_id on document
    for each row execute function retire_document_contents();
alter table document_upload add constraint source_reservation_exact
    check(status<>'pending' or purpose<>'source' or reserved_bytes=size);

alter table document_upload add constraint upload_content_owner
    foreign key(content_id,target_document_id) references document_content(id,document_id)
    deferrable initially deferred;
alter table document_upload add constraint output_not_processing check(purpose='source' or processing_profile is null);
create function require_upload_placement() returns trigger language plpgsql as $$
begin
    if new.target_document_id is not null and not exists(select 1 from document d
        where d.id=new.target_document_id and d.space_id=new.space_id
        and d.folder_id is not distinct from new.folder_id and d.session_id is not distinct from new.session_id
        and d.purpose=case when new.purpose='source' then 'source' else 'output' end) then
        raise exception 'file write must belong to its declared destination' using errcode='23514';
    end if;
    return new;
end $$;
create trigger upload_placement before insert or update of target_document_id,space_id,folder_id,session_id,purpose on document_upload
    for each row execute function require_upload_placement();

create index document_content_retention on document_content(published_at,id) where cleaned_at is not null;

-- Retirement can change many files at once. Aggregate by account instead of
-- writing the same hot budget row once per file in a large UPDATE.
create function account_document_updates() returns trigger language plpgsql as $$
declare movement record;
begin
    for movement in
        select changes.owner,sum(changes.bytes)::bigint as bytes from (
            select d.quota_owner as owner,coalesce(c.size,0) as bytes
                from new_documents d left join document_content c on c.id=d.current_content_id where d.deletion_id is null
            union all
            select d.quota_owner as owner,-coalesce(c.size,0) as bytes
                from old_documents d left join document_content c on c.id=d.current_content_id where d.deletion_id is null
        ) changes join space s on s.id=changes.owner
        group by changes.owner,s.organization_id having sum(changes.bytes)<>0
        order by s.organization_id,changes.owner
    loop
        perform change_storage_budget(movement.owner,movement.bytes,0);
    end loop;
    return null;
end $$;
create trigger document_updates_account after update on document
    referencing old table as old_documents new table as new_documents
    for each statement execute function account_document_updates();
