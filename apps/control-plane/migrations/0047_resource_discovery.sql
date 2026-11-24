-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Opt-in metadata disclosure belongs to each existing source definition. New
-- definitions, copies and marketplace installations retain the private default.
alter table prompt add column discoverable boolean not null default false;
alter table skill add column discoverable boolean not null default false;
alter table agent_instance add column discoverable boolean not null default false;

-- Organization discovery first selects spaces, then their opted-in definitions.
create index prompt_discoverable_space on prompt(space_id, prompt_id) where discoverable;
create index skill_discoverable_space on skill(space_id, skill_id) where discoverable;
create index agent_discoverable_space on agent_instance(space_id, agent_instance_id) where discoverable;

-- Placement is already immutable. This structural rule keeps every writer,
-- including provisioning, from accidentally exposing personal source metadata.
create function protect_resource_discovery() returns trigger language plpgsql as $$
begin
    if new.discoverable and exists(select 1 from space where id=new.space_id and kind='personal') then
        raise exception 'personal resources cannot be discoverable' using errcode='23514',
            constraint=TG_NAME, table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger prompt_discovery before insert or update of discoverable, space_id on prompt
    for each row execute function protect_resource_discovery();
create trigger skill_discovery before insert or update of discoverable, space_id on skill
    for each row execute function protect_resource_discovery();
create trigger agent_discovery before insert or update of discoverable, space_id on agent_instance
    for each row execute function protect_resource_discovery();
comment on trigger prompt_discovery on prompt is
    'assertion: consistency - personal resource metadata stays private';
comment on trigger skill_discovery on skill is
    'assertion: consistency - personal resource metadata stays private';
comment on trigger agent_discovery on agent_instance is
    'assertion: consistency - personal resource metadata stays private';

-- Disclosure edits are ordinary authored edits, without changing instruction or
-- agent-configuration revisions. Existing no-op attribution remains intact.
create or replace function protect_prompt_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if (new.prompt_id, new.space_id, new.logical_name, new.created_at, new.created_by)
            is distinct from
            (old.prompt_id, old.space_id, old.logical_name, old.created_at, old.created_by) then
            raise exception 'prompt identity and creation metadata are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.display_name, new.description, new.text, new.category_id, new.tags, new.discoverable)
            is distinct from (old.display_name, old.description, old.text, old.category_id, old.tags, old.discoverable) then
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;

create or replace function protect_agent_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.created_by is null or btrim(new.created_by) = '' then
            raise exception 'agent creation requires an author' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if new.logical_name is distinct from old.logical_name then
            raise exception 'agent logical name is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.agent_instance_id, new.space_id, new.template_id, new.source_runtime_id,
                new.source_agent_id, new.created_at, new.created_by)
            is distinct from
            (old.agent_instance_id, old.space_id, old.template_id, old.source_runtime_id,
                old.source_agent_id, old.created_at, old.created_by) then
            raise exception 'agent identity, placement and creation metadata are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.display_name, new.description, new.enabled, new.tuning, new.discoverable)
            is distinct from (old.display_name, old.description, old.enabled, old.tuning, old.discoverable) then
            if new.updated_by is null or btrim(new.updated_by) = '' then
                raise exception 'agent edit requires an author' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;
