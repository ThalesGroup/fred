-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- One canonical ASCII name per type and space. The prompt command is '/' || logical_name.
-- Reject noncanonical input instead of silently renaming resources or promotions.
create table prompt (
    prompt_id uuid primary key,
    space_id uuid not null references space (id) on delete cascade,
    logical_name text collate "C" not null
        check (logical_name ~ '^[a-z0-9_-]{1,64}$')
        check (logical_name <> 'skill'), -- Existing reserved slash command, not a skill schema.
    display_name varchar(255) not null check (btrim(display_name) <> ''),
    description text,
    text text not null,
    created_at timestamptz not null default now(),
    created_by text not null check (btrim(created_by) <> ''),
    updated_at timestamptz not null default now(),
    updated_by text not null check (btrim(updated_by) <> ''),
    constraint prompt_space_logical_name_key unique (space_id, logical_name)
);

create function protect_prompt_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if (new.prompt_id, new.space_id, new.logical_name, new.created_at, new.created_by)
            is distinct from
            (old.prompt_id, old.space_id, old.logical_name, old.created_at, old.created_by) then
            raise exception 'prompt identity and creation metadata are immutable' using errcode = '23514';
        end if;
        if (new.display_name, new.description, new.text)
            is distinct from (old.display_name, old.description, old.text) then
            -- The authenticated writer supplies updated_by; SQL is not an identity provider.
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;

create trigger prompt_definition before insert or update on prompt
    for each row execute function protect_prompt_definition();

-- The current agent writer does not provide a logical name yet. Do not derive an
-- identity from a mutable display label. The application lot must populate this
-- column, SET NOT NULL and drop uq_agent_instance_space_name together.
alter table agent_instance add column logical_name text collate "C"
    check (logical_name ~ '^[a-z0-9_-]{1,64}$');
alter table agent_instance add constraint agent_instance_space_logical_name_key
    unique (space_id, logical_name);

-- Historical author fields remain nullable: no invented attribution or backfill.
-- Authenticated creation and subsequent edits must supply their actual actor.
create function protect_agent_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.created_by is null or btrim(new.created_by) = '' then
            raise exception 'agent creation requires an author' using errcode = '23514';
        end if;
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        -- Only an unassigned name can be filled by the explicit naming step.
        if old.logical_name is not null and new.logical_name is distinct from old.logical_name then
            raise exception 'agent logical name is immutable' using errcode = '23514';
        end if;
        if (new.agent_instance_id, new.space_id, new.template_id, new.source_runtime_id,
                new.source_agent_id, new.created_at, new.created_by)
            is distinct from
            (old.agent_instance_id, old.space_id, old.template_id, old.source_runtime_id,
                old.source_agent_id, old.created_at, old.created_by) then
            raise exception 'agent identity, placement and creation metadata are immutable'
                using errcode = '23514';
        end if;
        if (new.display_name, new.description, new.enabled, new.tuning)
            is distinct from (old.display_name, old.description, old.enabled, old.tuning) then
            if new.updated_by is null or btrim(new.updated_by) = '' then
                raise exception 'agent edit requires an author' using errcode = '23514';
            end if;
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;

create trigger agent_definition before insert or update on agent_instance
    for each row execute function protect_agent_definition();

-- Historical sessions whose agent has disappeared retain an explicitly unknown origin.
-- No FK: both agent and deployment space may be purged independently of chat history.
alter table session_metadata add column agent_space_id uuid;
update session_metadata s set agent_space_id = a.space_id
    from agent_instance a where a.agent_instance_id = s.agent_instance_id;

do $$
begin
    if exists (
        select 1 from session_metadata s
        join space c on c.id = s.space_id
        join space a on a.id = s.agent_space_id
        where c.organization_id <> a.organization_id
    ) then
        raise exception 'existing conversation and agent belong to different organizations'
            using errcode = '23514';
    end if;
end $$;

create function protect_session_association() returns trigger language plpgsql as $$
declare
    deployment uuid;
    agent_organization uuid;
    chat_organization uuid;
    agent_template uuid;
    agent_runtime text;
begin
    if tg_op = 'INSERT' then
        -- Hold the association's sources through commit, including against concurrent purge.
        select a.space_id, sa.organization_id, sc.organization_id, a.template_id, a.source_runtime_id
            into deployment, agent_organization, chat_organization, agent_template, agent_runtime
            from agent_instance a
            join space sa on sa.id = a.space_id
            join space sc on sc.id = new.space_id
            where a.agent_instance_id = new.agent_instance_id
            for key share of a, sa, sc;
        if not found then
            raise exception 'conversation requires an existing agent and conversation space'
                using errcode = '23503';
        end if;
        if (new.agent_space_id is not null and new.agent_space_id <> deployment)
            or agent_organization <> chat_organization
            or new.template_id <> agent_template or new.runtime_id <> agent_runtime then
            raise exception 'conversation agent association is inconsistent' using errcode = '23514';
        end if;
        new.agent_space_id := deployment;
    elsif (new.session_id, new.space_id, new.user_id, new.agent_instance_id,
            new.agent_space_id, new.template_id, new.runtime_id)
        is distinct from
          (old.session_id, old.space_id, old.user_id, old.agent_instance_id,
            old.agent_space_id, old.template_id, old.runtime_id) then
        raise exception 'conversation ownership and agent association are immutable'
            using errcode = '23514';
    end if;
    return new;
end $$;

create trigger session_association before insert or update on session_metadata
    for each row execute function protect_session_association();
