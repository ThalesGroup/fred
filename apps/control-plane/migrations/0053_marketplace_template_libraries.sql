-- A Word library contributes several originals to the existing immutable proposal.
-- Typed relations retain document authority; package JSON is verified against them.
create table marketplace_proposal_original (
    proposal_id uuid not null references marketplace_proposal(proposal_id) on delete cascade,
    document_id uuid not null unique references document(id) on delete cascade,
    primary key(proposal_id,document_id)
);
insert into marketplace_proposal_original select proposal_id,document_id from marketplace_proposal where document_id is not null;
create or replace function protect_marketplace_document() returns trigger language plpgsql as $$
declare descriptor jsonb; count_files integer;
begin
    if tg_op='UPDATE' and new.document_id is distinct from old.document_id and
        (new.document_id is not null or exists(select 1 from document where id=old.document_id)) then
        raise exception 'only cleanup detaches a marketplace original' using errcode='23514';
    end if;
    if new.package is not null then
        select count(*) into count_files from jsonb_path_query(new.package,'$.content.capabilities.*.files.*');
        if count_files>9 or (count_files>0)<>(new.document_id is not null) or
            (select count(distinct f.value->>'document_id') from jsonb_path_query(new.package,'$.content.capabilities.*.files.*') f(value))<>count_files then
            raise exception 'invalid marketplace original set' using errcode='23514';
        end if;
        if new.document_id is not null and not exists(select 1 from jsonb_path_query(new.package,'$.content.capabilities.*.files.*') f(value) where f.value->>'document_id'=new.document_id::text) then
            raise exception 'missing marketplace primary original' using errcode='23514';
        end if;
        for descriptor in select value from jsonb_path_query(new.package,'$.content.capabilities.*.files.*') f(value) loop
            if not exists(select 1 from document d join document_content c on c.id=d.current_content_id
                join document_upload u on u.id=d.id where d.id::text=descriptor->>'document_id'
                and d.space_id=new.marketplace_space_id and d.purpose='marketplace' and d.deletion_id is null
                and c.cleaned_at is null and c.published_at is not null and u.purpose='marketplace'
                and u.status='stored' and not u.put_pending and u.target_document_id=d.id and u.content_id=c.id
                and (u.size,u.sha256,u.mime,u.object_key)=(c.size,c.sha256,c.mime,c.object_key)
                and descriptor->>'name'=d.name and descriptor->>'mime'=c.mime
                and descriptor->>'size'=c.size::text and descriptor->>'sha256'=c.sha256) then
                raise exception 'a marketplace package owns its verified organization originals' using errcode='23514';
            end if;
        end loop;
    end if;
    return new;
end $$;
create function bind_marketplace_originals() returns trigger language plpgsql as $$
begin
    insert into marketplace_proposal_original(proposal_id,document_id)
        select new.proposal_id,(f.value->>'document_id')::uuid
        from jsonb_path_query(new.package,'$.content.capabilities.*.files.*') f(value);
    return new;
end $$;
create trigger marketplace_originals after insert on marketplace_proposal for each row execute function bind_marketplace_originals();
create or replace function forbid_document_copy_change() returns trigger language plpgsql as $$
begin
    if new.current_content_id is null and (old.purpose='wiki' or not exists(
        select 1 from marketplace_proposal_original o join marketplace_proposal p using(proposal_id)
        where o.document_id=old.id and p.package is not null)) then return new; end if;
    raise exception 'a published copy is frozen' using errcode='23514';
end $$;
create or replace function retire_marketplace_document() returns trigger language plpgsql as $$
begin
    update document set current_content_id=null,updated_at=clock_timestamp()
        where id in (select (f.value->>'document_id')::uuid
            from jsonb_path_query(old.package,'$.content.capabilities.*.files.*') f(value))
        and deletion_id is null;
    return null;
end $$;
-- Existing proposal retirement/delete triggers also retire every library original.
comment on trigger marketplace_originals on marketplace_proposal is
    'effect: bind every verified configuration original to its immutable proposal';
