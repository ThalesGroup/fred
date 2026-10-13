-- Ownership tree, folder classification and document registry.
-- Rights never live here: OpenFGA holds direct roles on spaces only.

create type space_kind as enum ('organization', 'team', 'project');

create table space (
    id             uuid primary key,
    kind           space_kind not null,
    name           text not null,
    parent_id      uuid references space (id),
    personal_owner text,          -- set only for a personal space: a one-member team
    path           uuid[] not null, -- ancestors then self; this is the search scope
    created_at     timestamptz not null default now(),
    check ((kind = 'organization') = (parent_id is null)),
    check (personal_owner is null or kind = 'team'),
    check (path[array_length(path, 1)] = id),
    unique nulls not distinct (parent_id, name),
    unique (parent_id, personal_owner)
);

create table folder (
    id         uuid primary key,
    space_id   uuid not null references space (id),
    parent_id  uuid,
    name       text not null,
    path       text not null,     -- '/<id>/<id>/', ids only, copied into every chunk
    created_at timestamptz not null default now(),
    unique (id, space_id),
    foreign key (parent_id, space_id) references folder (id, space_id),
    unique nulls not distinct (space_id, parent_id, name)
);

create table document (
    id         uuid primary key,
    space_id   uuid not null references space (id),
    folder_id  uuid,              -- null means the space root
    name       text not null,
    mime       text not null,
    size       bigint not null,
    sha256     text not null,
    created_by text not null,
    created_at timestamptz not null default now(),
    foreign key (folder_id, space_id) references folder (id, space_id),
    unique nulls not distinct (space_id, folder_id, name)
);

-- Placement is immutable: chunks and storage keys copy it. Only names change.
create function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.parent_id, new.path, new.personal_owner)
       is distinct from (old.kind, old.parent_id, old.path, old.personal_owner) then
        raise exception 'space placement is immutable';
    end if;
    return new;
end $$;

create function forbid_folder_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.parent_id, new.path) is distinct from (old.space_id, old.parent_id, old.path) then
        raise exception 'folder placement is immutable';
    end if;
    return new;
end $$;

create function forbid_document_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.folder_id) is distinct from (old.space_id, old.folder_id) then
        raise exception 'document placement is immutable';
    end if;
    return new;
end $$;

create trigger space_immutable before update on space for each row execute function forbid_space_move();
create trigger folder_immutable before update on folder for each row execute function forbid_folder_move();
create trigger document_immutable before update on document for each row execute function forbid_document_move();
