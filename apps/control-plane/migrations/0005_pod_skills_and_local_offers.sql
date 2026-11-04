-- Skills are pod offers, not organization-owned content. Their descriptor and
-- snapshot revision share the existing inventory and organization authorization.
alter table runtime_catalog add column skills_revision text,
    add column skills_availability text check (skills_availability in ('available', 'disabled', 'unavailable'));

-- A missing policy inherits the parent's ceiling. A present empty allow-list
-- denies every offer. Retain an inherit row after reset so stale editors cannot
-- recreate an old revision (ABA). The organization remains the root authority.
create table space_capability_policy (
    space_id uuid not null references space(id) on delete cascade,
    runtime_id text not null references runtime_catalog(runtime_id),
    revision bigint not null check (revision > 0),
    restricted boolean not null,
    updated_by text not null check (btrim(updated_by) <> ''),
    updated_at timestamptz not null default clock_timestamp(),
    primary key (space_id, runtime_id)
);
create table space_capability_permission (
    space_id uuid not null,
    runtime_id text not null,
    capability_id text not null,
    primary key (space_id, runtime_id, capability_id),
    foreign key (space_id, runtime_id) references space_capability_policy(space_id, runtime_id) on delete cascade,
    foreign key (runtime_id, capability_id) references runtime_capability(runtime_id, capability_id)
);
create function require_local_capability_space() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.space_id and kind in ('team', 'project')) then
        raise exception 'local offer policy requires a team or project' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger space_capability_policy_kind before insert or update of space_id
    on space_capability_policy for each row execute function require_local_capability_space();
