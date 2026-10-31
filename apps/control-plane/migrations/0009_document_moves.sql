-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Preparation only: document_immutable still forbids changing document placement.
-- These receipts neither move data nor schedule work; activation needs the SQL/index writer.
create table document_move (
    id uuid primary key,
    document_id uuid not null references document(id) on delete cascade,
    actor text not null check (btrim(actor) <> ''),
    source_space_id uuid not null,
    source_folder_id uuid,
    destination_space_id uuid not null,
    destination_folder_id uuid,
    generation_id uuid,
    phase text not null default 'requested'
        check (phase in ('requested', 'projecting', 'completed', 'cancelled')),
    created_at timestamptz not null default now() check (isfinite(created_at)),
    finished_at timestamptz check (isfinite(finished_at)),
    check ((phase in ('completed', 'cancelled')) = (finished_at is not null)),
    check (finished_at >= created_at),
    check ((source_space_id, source_folder_id)
        is distinct from (destination_space_id, destination_folder_id))
);
create unique index document_move_active on document_move(document_id)
    where phase in ('requested', 'projecting');
create index document_move_history on document_move(document_id, created_at desc, id);

-- Placement/generation are historical facts, not permanent FKs that block purge.
-- Only the document owns the receipt; its definitive purge removes the receipts.
create function protect_document_move() returns trigger language plpgsql as $$
declare
    source document%rowtype;
    source_organization uuid;
    destination_organization uuid;
begin
    if tg_op = 'INSERT' then
        if new.phase <> 'requested' or new.finished_at is not null then
            raise exception 'a document move starts as requested' using errcode = '23514';
        end if;
        select * into source from document where id = new.document_id for update;
        if not found then
            raise exception 'document move requires an existing document' using errcode = '23503';
        end if;
        if source.session_id is not null or source.deletion_id is not null then
            raise exception 'only live drive documents can be moved' using errcode = '23514';
        end if;
        if source.retrievable_pending or exists (
            select 1 from document_processing where document_id = source.id
                and status in ('pending', 'running')
        ) then
            raise exception 'document has unfinished processing or inclusion work' using errcode = '23514';
        end if;
        select organization_id into source_organization
            from space where id = source.space_id and deletion_id is null for share;
        if not found then
            raise exception 'source space must be live' using errcode = '23514';
        end if;
        select organization_id into destination_organization
            from space where id = new.destination_space_id and deletion_id is null for share;
        if not found then
            raise exception 'destination space must exist and be live' using errcode = '23503';
        end if;
        if source_organization <> destination_organization then
            raise exception 'document move must stay within one organization' using errcode = '23514';
        end if;
        if new.destination_folder_id is not null then
            perform 1 from folder where id = new.destination_folder_id
                and space_id = new.destination_space_id and deletion_id is null for share;
            if not found then
                raise exception 'destination folder must be live in destination space' using errcode = '23503';
            end if;
        end if;
        -- Always capture database facts, never source placement asserted by the caller.
        new.source_space_id := source.space_id;
        new.source_folder_id := source.folder_id;
        new.generation_id := source.published_generation;
    else
        if (new.id, new.document_id, new.actor, new.source_space_id, new.source_folder_id,
                new.destination_space_id, new.destination_folder_id, new.generation_id, new.created_at)
            is distinct from
            (old.id, old.document_id, old.actor, old.source_space_id, old.source_folder_id,
                old.destination_space_id, old.destination_folder_id, old.generation_id, old.created_at) then
            raise exception 'document move request is immutable' using errcode = '23514';
        end if;
        if new.phase = old.phase then
            if new.finished_at is distinct from old.finished_at then
                raise exception 'document move outcome is immutable' using errcode = '23514';
            end if;
            return new;
        end if;
        if not ((old.phase = 'requested' and new.phase in ('projecting', 'cancelled'))
            or (old.phase = 'projecting' and new.phase = 'completed')) then
            raise exception 'invalid document move transition' using errcode = '23514';
        end if;
        if new.phase in ('projecting', 'completed') then
            select * into source from document where id = new.document_id for update;
            if not found then
                raise exception 'document move requires an existing document' using errcode = '23503';
            end if;
            if (source.space_id, source.folder_id, source.published_generation)
                is distinct from
                (new.destination_space_id, new.destination_folder_id, new.generation_id)
                or source.session_id is not null or source.deletion_id is not null then
                raise exception 'document move placement or generation does not match' using errcode = '23514';
            end if;
        end if;
        if new.phase in ('completed', 'cancelled') then
            new.finished_at := clock_timestamp();
        end if;
    end if;
    return new;
end $$;
create trigger document_move_identity before insert or update on document_move
    for each row execute function protect_document_move();
