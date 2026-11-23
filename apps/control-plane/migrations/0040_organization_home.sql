-- Organization presentation settings confer no rights over the selected agents.
create table organization_home_settings (
    organization_id uuid primary key references space(id) on delete cascade,
    layout text not null check (layout in ('classic', 'advanced')),
    updated_by text not null,
    updated_at timestamptz not null default now()
);
create trigger home_settings_organization before insert or update of organization_id
    on organization_home_settings for each row execute function require_organization_space();

create table organization_home_agent (
    organization_id uuid not null references organization_home_settings(organization_id) on delete cascade,
    -- -1 is the question launcher; 0..9 are the ordered featured agents.
    position smallint not null check (position between -1 and 9),
    agent_instance_id uuid not null references agent_instance(agent_instance_id) on delete cascade,
    badge text check (char_length(badge) between 1 and 20 and badge = btrim(badge)),
    highlights text[] not null default '{}' check (cardinality(highlights) <= 4
        and char_length(array_to_string(highlights, '')) <= 320),
    primary key (organization_id, position),
    check (position >= 0 or (badge is null and cardinality(highlights) = 0))
);
create unique index organization_home_featured_once
    on organization_home_agent(organization_id, agent_instance_id) where position >= 0;
create index organization_home_agent_instance on organization_home_agent(agent_instance_id);

create function protect_organization_home_agent() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from agent_instance a join space s on s.id=a.space_id
        where a.agent_instance_id=new.agent_instance_id and s.organization_id=new.organization_id
        and s.kind in ('team', 'project')) then
        raise exception 'home agent must belong to a team or project in the organization' using errcode='23514';
    end if;
    return new;
end $$;
create trigger organization_home_agent_placement before insert or update
    on organization_home_agent for each row execute function protect_organization_home_agent();
comment on trigger home_settings_organization on organization_home_settings is
    'assertion: consistency - home settings belong to an organization';
comment on trigger organization_home_agent_placement on organization_home_agent is
    'assertion: consistency - home agents belong to teams or projects of the same organization';
