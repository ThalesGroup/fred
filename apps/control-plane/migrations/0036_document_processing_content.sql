-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh installations only. Reuse immutable file contents and the upload journal;
-- replacement admission remains an internal foundation, not a public upload API.
set local lock_timeout = '5s';

alter table document_processing add column content_id uuid not null;
alter table document_processing add column expected_content_id uuid not null;
-- A compare-and-swap snapshot, not a retention reference to an old generation.
alter table document_processing add column expected_generation_id uuid;
alter table document_processing add constraint processing_content_owner
    foreign key(content_id,document_id) references document_content(id,document_id);
alter table document_processing add constraint processing_expected_content_owner
    foreign key(expected_content_id,document_id) references document_content(id,document_id);
create index document_processing_content on document_processing(content_id);
create index document_processing_expected_content on document_processing(expected_content_id);
drop index document_processing_success;
create unique index generation_committed_stage on generation(processing_id,stage)
    where committed_at is not null;

create or replace function protect_processing_identity() returns trigger language plpgsql as $$
begin
    if (new.actor,new.request_key,new.document_id,new.content_id,new.expected_content_id,new.expected_generation_id,
        new.profile,new.workflow_id,new.retry_of,new.submission,new.profile_settings,
        new.preparation_seconds,new.extraction_seconds,new.indexing_seconds)
        is distinct from
        (old.actor,old.request_key,old.document_id,old.content_id,old.expected_content_id,old.expected_generation_id,
        old.profile,old.workflow_id,old.retry_of,old.submission,old.profile_settings,
        old.preparation_seconds,old.extraction_seconds,old.indexing_seconds) then
        raise exception 'processing identity is immutable' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    if old.status in ('succeeded','failed') and (new.status,new.stage,new.completed_at,new.error_code)
        is distinct from (old.status,old.stage,old.completed_at,old.error_code) then
        raise exception 'processing outcome is final' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_processing_source() returns trigger language plpgsql as $$
begin
    if not exists(select 1 from document d join document_content c
        on c.document_id=d.id and c.id=new.content_id
        where d.id=new.document_id and d.purpose='source' and d.deletion_id is null
        and not d.retrievable_pending
        and d.current_content_id=new.expected_content_id
        and d.published_generation is not distinct from new.expected_generation_id
        and c.kind='primary' and c.published_at is not null
        and c.cleaned_at is null and c.cleanup_after is null
        and (c.id=d.current_content_id or exists(select 1 from document_upload u
            join document_content previous on previous.id=d.current_content_id
            where u.content_id=c.id and u.target_document_id=d.id and u.purpose='source'
            and u.status='stored' and not u.put_pending
            and (u.size,u.sha256,u.object_key)=(c.size,c.sha256,c.object_key)
            and u.expected_content_id=d.current_content_id
            and u.reserved_bytes=greatest(c.size-previous.size,0)))) then
        raise exception 'processing requires live owned content and its current publication snapshot' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    return new;
end $$;

alter table document_upload drop constraint source_reservation_exact;
create function require_source_reservation() returns trigger language plpgsql as $$
declare previous_size bigint;
begin
    if new.purpose<>'source' then return new; end if;
    -- Parent purge detaches receipt references after processing released growth.
    if new.status<>'pending' and new.reserved_bytes=0 and not exists
        (select 1 from document where id=new.target_document_id) then return new; end if;
    if new.expected_content_id is null then
        if new.status='pending' and new.reserved_bytes<>new.size then
            raise exception 'new source reservation must cover all bytes' using errcode='23514',
                constraint=TG_NAME, table=TG_TABLE_NAME;
        end if;
    else
        select size into previous_size from document_content
            where id=new.expected_content_id and document_id=new.target_document_id and kind='primary';
        if previous_size is null or (new.status='pending' or (new.status='stored' and new.reserved_bytes>0))
            and new.reserved_bytes<>greatest(new.size-previous_size,0) then
            raise exception 'replacement reservation must cover positive growth' using errcode='23514',
                constraint=TG_NAME, table=TG_TABLE_NAME;
        end if;
        if new.status='stored' and new.reserved_bytes=0 and new.size>previous_size
            and not exists(select 1 from document_processing p
                where p.content_id=new.content_id and p.document_id=new.target_document_id
                and p.expected_content_id=new.expected_content_id and p.status in ('succeeded','failed')) then
            raise exception 'replacement growth remains reserved until processing is terminal' using errcode='23514',
                constraint=TG_NAME, table=TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;
create trigger document_upload_source_reservation before insert or update on document_upload
    for each row execute function require_source_reservation();
comment on trigger document_upload_source_reservation on document_upload is
    'assertion: consistency - source uploads reserve initial bytes or replacement growth';

create or replace function account_document_upload() returns trigger language plpgsql as $$
declare before_bytes bigint:=0; after_bytes bigint:=0;
begin
    if tg_op<>'INSERT' and (old.status='pending' or
        (old.status='stored' and old.purpose='source' and old.expected_content_id is not null)) then
        before_bytes:=old.reserved_bytes;
    end if;
    if tg_op<>'DELETE' and (new.status='pending' or
        (new.status='stored' and new.purpose='source' and new.expected_content_id is not null)) then
        after_bytes:=new.reserved_bytes;
    end if;
    perform change_storage_budget(case when tg_op='DELETE' then old.quota_owner else new.quota_owner end,
        0,after_bytes-before_bytes);
    return null;
end $$;

-- Terminal processing and publication belong to one application transaction.
-- A failed candidate is never readmitted: its immutable bytes enter cleanup.
create function finish_processing_content() returns trigger language plpgsql as $$
begin
    if old.status in ('pending','running') and new.status in ('succeeded','failed')
        and new.content_id<>new.expected_content_id then
        update document_upload set reserved_bytes=0
            where content_id=new.content_id and target_document_id=new.document_id
            and expected_content_id=new.expected_content_id and purpose='source' and status='stored';
        if new.status='failed' then
            update document_content set cleanup_after=greatest(clock_timestamp(),
                (select max(expires_at)+interval '60 seconds' from generation where processing_id=new.id))
                where id=new.content_id and not exists(select 1 from document
                    where current_content_id=new.content_id and deletion_id is null);
        end if;
    end if;
    return null;
end $$;
create trigger document_processing_content_finished after update of status on document_processing
    for each row execute function finish_processing_content();
comment on trigger document_processing_content_finished on document_processing is
    'effect: release replacement growth reservation and schedule failed candidate cleanup';

create or replace function protect_document_content() returns trigger language plpgsql as $$
begin
    if (new.id,new.document_id,new.kind,new.source_content_id,new.object_key,new.mime,new.size,new.sha256)
        is distinct from (old.id,old.document_id,old.kind,old.source_content_id,old.object_key,old.mime,old.size,old.sha256)
        or (old.published_at is not null and new.published_at is distinct from old.published_at)
        or (old.cleanup_after is not null and new.cleanup_after is null)
        or (old.cleaned_at is not null and new.cleaned_at is distinct from old.cleaned_at) then
        raise exception 'file content is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.cleaned_at is not null and exists(select 1 from document d where d.id=new.document_id
        and d.deletion_id is null and (d.current_content_id=new.id or d.current_content_id=new.source_content_id)) then
        raise exception 'current content cannot be cleaned' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.cleaned_at is not null and exists(select 1 from document_processing p
        where p.status in ('pending','running')
        and (p.content_id=new.id or p.expected_content_id=new.id)) then
        raise exception 'active processing content cannot be cleaned' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_document_current() returns trigger language plpgsql as $$
begin
    if new.current_content_id is not null and new.deletion_id is null and not exists
        (select 1 from document_content c where c.id=new.current_content_id and c.document_id=new.id
         and c.kind='primary' and c.published_at is not null and c.cleaned_at is null
         and c.cleanup_after is null) then
        raise exception 'current file content must be live, published and owned' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    if tg_op='UPDATE' then
        if new.purpose is distinct from old.purpose or new.quota_owner is distinct from old.quota_owner then
            raise exception 'file purpose and quota owner are immutable' using errcode='23514',
                constraint=TG_NAME, table=TG_TABLE_NAME;
        end if;
        if new.deletion_id is null and new.purpose='source' and
            (new.published_generation is distinct from old.published_generation or
             (old.current_content_id is not null and new.current_content_id is distinct from old.current_content_id))
            and not exists(select 1 from generation g join document_processing p on p.id=g.processing_id
                where g.id=new.published_generation and g.document_id=new.id
                and g.stage='indexing' and g.committed_at is not null and p.status='succeeded'
                and p.content_id=new.current_content_id and p.expected_content_id=old.current_content_id
                and p.expected_generation_id is not distinct from old.published_generation
                and (new.retrieval_id is null or new.retrieval_confirmed)
                and (p.content_id=p.expected_content_id or exists(select 1 from document_upload u
                    where u.content_id=p.content_id and u.target_document_id=p.document_id
                    and u.expected_content_id=p.expected_content_id and u.purpose='source'
                    and u.status='stored' and not u.put_pending and u.reserved_bytes=0))) then
            raise exception 'source publication requires a successful exact-content compare-and-swap' using errcode='23514',
                constraint=TG_NAME, table=TG_TABLE_NAME;
        end if;
    elsif new.published_generation is not null then
        raise exception 'initial document cannot already have a generation' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
comment on trigger document_current_valid on document is
    'assertion: consistency - live owned content and atomic exact-content source publication';

create or replace function retire_document_contents() returns trigger language plpgsql as $$
begin
    if new.deletion_id is distinct from old.deletion_id and new.deletion_id is not null then
        update document_content set cleanup_after=(select due_at from deletion where id=new.deletion_id)
            where document_id=new.id and cleaned_at is null;
    elsif new.current_content_id is distinct from old.current_content_id then
        update document_content set cleanup_after=clock_timestamp()
            where document_id=new.id and (id=old.current_content_id or source_content_id=old.current_content_id)
                and cleaned_at is null;
    end if;
    if new.published_generation is distinct from old.published_generation then
        update generation set cleaned_at=null,cleanup_cursor=0,
            cleanup_after=greatest(clock_timestamp(),expires_at+interval '60 seconds')
            where id=old.published_generation;
    end if;
    return null;
end $$;
drop trigger document_contents_retirement on document;
create trigger document_contents_retirement after update of current_content_id,published_generation,deletion_id on document
    for each row execute function retire_document_contents();
comment on trigger document_contents_retirement on document is
    'effect: schedule retired contents and superseded generation cleanup';
