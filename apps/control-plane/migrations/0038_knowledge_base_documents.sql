-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
set local lock_timeout = '5s';

alter table document_upload add column kb_run_id uuid references kb_run(id) on delete set null;
alter table document_upload add column source_key text;
alter table document_upload add column source_version text;
alter table document_upload add constraint kb_upload_source check (
    (kb_run_id is null and source_key is null and source_version is null) or
    (source_key is not null and length(source_key) between 1 and 2048
        and source_version is not null and length(source_version) between 1 and 512));
alter table document_processing add column kb_run_id uuid references kb_run(id);
create index document_upload_kb_run on document_upload(kb_run_id) where kb_run_id is not null;
create index document_processing_kb_run on document_processing(kb_run_id) where kb_run_id is not null;

-- One stable source identity; transfer history remains in the existing upload journal.
create table kb_source_document (
    instance_id uuid not null references kb_instance(id) on delete cascade,
    source_key text collate "C" not null check(length(source_key) between 1 and 2048),
    document_id uuid unique references document(id) on delete set null,
    current_version text,
    pending_version text,
    pending_upload_id uuid references document_upload(id) on delete set null,
    pending_processing_id uuid references document_processing(id) on delete set null,
    last_seen_run_id uuid references kb_run(id),
    primary key(instance_id,source_key)
);
create index kb_source_upload on kb_source_document(pending_upload_id);
create index kb_source_processing on kb_source_document(pending_processing_id);

create function protect_kb_document_scope() returns trigger language plpgsql as $$
begin
    if tg_table_name='document_upload' then
        if tg_op='UPDATE' and (new.kb_run_id,new.source_key,new.source_version)
            is distinct from (old.kb_run_id,old.source_key,old.source_version)
            and not (new.kb_run_id is null and old.kb_run_id is not null
                and (new.source_key,new.source_version)=(old.source_key,old.source_version)
                and not exists(select 1 from kb_run where id=old.kb_run_id)) then
            raise exception 'source transfer identity is immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.kb_run_id is not null and not exists(select 1 from kb_run r
            where r.id=new.kb_run_id and r.space_id=new.space_id and r.folder_id=new.folder_id
                and new.session_id is null and new.purpose='source') then
            raise exception 'source transfer must match its run' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    elsif tg_table_name='document_processing' then
        if tg_op='UPDATE' and new.kb_run_id is distinct from old.kb_run_id then
            raise exception 'processing run is immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if tg_op='INSERT' and new.kb_run_id is not null and not exists(select 1 from document_upload u
            where u.kb_run_id=new.kb_run_id and u.target_document_id=new.document_id
                and u.content_id=new.content_id and u.status='stored') then
            raise exception 'processing must use its admitted source upload' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    else
        if tg_op='UPDATE' and (new.instance_id,new.source_key) is distinct from (old.instance_id,old.source_key) then
            raise exception 'source identity is immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.document_id is not null and not exists(select 1 from document d join kb_instance i
            on i.id=new.instance_id where d.id=new.document_id and d.folder_id=i.folder_id
                and d.space_id=i.space_id and d.purpose='source' and d.session_id is null) then
            raise exception 'source document must match its instance' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.pending_upload_id is not null and not exists(select 1 from document_upload u join kb_run r on r.id=u.kb_run_id
            where u.id=new.pending_upload_id and r.instance_id=new.instance_id and u.source_key=new.source_key
                and u.source_version=new.pending_version) then
            raise exception 'source candidate must match its transfer' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.last_seen_run_id is not null and not exists(select 1 from kb_run where id=new.last_seen_run_id and instance_id=new.instance_id) then
            raise exception 'source observation must match its instance' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.pending_processing_id is not null and not exists(select 1 from document_processing p join kb_run r on r.id=p.kb_run_id
            join document_upload u on u.id=new.pending_upload_id where p.id=new.pending_processing_id
                and r.instance_id=new.instance_id and p.document_id=new.document_id
                and u.content_id=p.content_id and u.kb_run_id=p.kb_run_id and u.source_key=new.source_key) then
            raise exception 'source processing must match its transfer' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        if new.document_id is null then new.current_version:=null; end if;
        if new.current_version is not null and (tg_op='INSERT' or new.current_version is distinct from old.current_version)
            and not exists(select 1 from document_processing p join document d on d.id=p.document_id
                where p.id=new.pending_processing_id and p.document_id=new.document_id
                    and p.status='succeeded' and p.content_id=d.current_content_id and new.current_version=new.pending_version) then
            raise exception 'source version requires successful publication' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;
create trigger kb_upload_scope before insert or update on document_upload for each row execute function protect_kb_document_scope();
comment on trigger kb_upload_scope on document_upload is 'assertion: consistency - immutable source transfer bound to its run';
create trigger kb_processing_scope before insert or update on document_processing for each row execute function protect_kb_document_scope();
comment on trigger kb_processing_scope on document_processing is 'assertion: consistency - immutable processing run and source content';
create trigger kb_source_scope before insert or update on kb_source_document for each row execute function protect_kb_document_scope();
comment on trigger kb_source_scope on kb_source_document is 'assertion: consistency - source identity, placement and published version';

create function protect_kb_source_placement() returns trigger language plpgsql as $$
begin
    if tg_table_name='document' then
        if (new.space_id,new.folder_id,new.name) is distinct from (old.space_id,old.folder_id,old.name)
            and exists(select 1 from kb_source_document where document_id=old.id) then
            raise exception 'managed source placement is immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    elsif exists(select 1 from kb_source_document where document_id=new.document_id)
        or exists(select 1 from kb_instance where folder_id=new.destination_folder_id) then
        raise exception 'managed source cannot move' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger kb_source_placement before update on document for each row execute function protect_kb_source_placement();
comment on trigger kb_source_placement on document is 'assertion: consistency - managed source placement and name are immutable';
create trigger kb_source_move before insert on document_move for each row execute function protect_kb_source_placement();
comment on trigger kb_source_move on document_move is 'assertion: consistency - managed source cannot move or receive manual moves';
