-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

alter table space add constraint space_placement_shape check (
    (kind = 'organization' and organization_id = id and parent_id is null)
    or (kind = 'personal' and organization_id <> id and parent_id is null)
    or (kind = 'team' and organization_id <> id and parent_id is not null
        and parent_id = organization_id)
    or (kind = 'project' and organization_id <> id and parent_id is not null
        and parent_id <> id)
);

alter table space add constraint space_id_organization_key unique (id, organization_id);
alter table space add constraint space_parent_organization_fkey
    foreign key (parent_id, organization_id) references space (id, organization_id);

-- Retired siblings keep their names until purge, as in the application contract.
create unique index space_sibling_name on space (parent_id, name)
    where kind in ('team', 'project');

-- Referenced kinds and placement are immutable; only creation needs this check.
create function require_space_hierarchy() returns trigger language plpgsql as $$
begin
    if new.kind <> 'organization' and not exists (
        select 1 from space where id = new.organization_id and kind = 'organization'
    ) then
        raise exception 'space requires an organization root' using errcode = '23514';
    end if;
    if new.kind = 'project' and not exists (
        select 1 from space where id = new.parent_id and kind = 'team'
    ) then
        raise exception 'project requires a team parent' using errcode = '23514';
    end if;
    return new;
end $$;

create trigger space_hierarchy after insert on space
    for each row execute function require_space_hierarchy();

create function require_space_role_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
    target_owner text;
begin
    select kind, personal_owner into target_kind, target_owner from space where id = new.space_id;
    if target_kind = 'personal' and target_owner <> new.subject then
        raise exception 'personal space roles require its owner' using errcode = '23514';
    end if;
    if new.role = 'organization_admin' and target_kind <> 'organization' then
        raise exception 'organization admin requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;

create trigger space_role_scope before insert or update of space_id, subject, role
    on space_role_grant for each row execute function require_space_role_scope();

-- Triggers protect future writes; reject pre-existing contradictions as well.
do $$
begin
    if exists (
        select 1 from space s join space o on o.id = s.organization_id
        where o.kind <> 'organization'
    ) or exists (
        select 1 from space s join space p on p.id = s.parent_id
        where s.kind = 'project' and p.kind <> 'team'
    ) then
        raise exception 'existing space hierarchy is invalid' using errcode = '23514';
    end if;
    if exists (
        select 1 from space_role_grant r join space s on s.id = r.space_id
        where s.kind = 'personal' and s.personal_owner <> r.subject
    ) then
        raise exception 'existing personal space grant is invalid' using errcode = '23514';
    end if;
    if exists (
        select 1 from space_role_grant r join space s on s.id = r.space_id
        where r.role = 'organization_admin' and s.kind <> 'organization'
    ) then
        raise exception 'existing organization admin scope is invalid' using errcode = '23514';
    end if;
end $$;
