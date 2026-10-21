-- Fresh installations only: existing placements require a separate FGA backfill.
-- Refuse populated installations rather than guess organizations or reset data.
do $$
begin
    if exists (select 1 from space) then
        raise exception 'space placement migration requires an empty space table; existing installations need an explicit OpenFGA backfill';
    end if;
end $$;

alter table space
    add column organization_id uuid not null references space (id),
    add column parent_id uuid references space (id);
create index space_organization on space (organization_id);
create index space_parent on space (parent_id);

create or replace function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.personal_owner, new.organization_id, new.parent_id)
        is distinct from (old.kind, old.personal_owner, old.organization_id, old.parent_id) then
        raise exception 'space placement is immutable';
    end if;
    return new;
end $$;
