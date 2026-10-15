-- The space tree moves to OpenFGA `parent` relations. Dropping the columns also drops
-- the root/parent check, sibling uniqueness and the self foreign key. Sibling names and
-- one personal space per organization are enforced under the organization lock.
alter table space drop column parent_id, drop column path;

create unique index space_organization_name on space (name) where kind = 'organization';

create or replace function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.personal_owner) is distinct from (old.kind, old.personal_owner) then
        raise exception 'space placement is immutable';
    end if;
    return new;
end $$;
