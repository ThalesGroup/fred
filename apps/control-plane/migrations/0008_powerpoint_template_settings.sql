-- Corrections belong to the organization's ppt_builder offer, including when
-- it uses the built-in deck (no uploaded file). File/preparation ownership is unchanged.
create table organization_powerpoint_settings (
    organization_id uuid not null references space(id) on delete cascade,
    runtime_id text not null,
    capability_id text not null default 'ppt_builder' check (capability_id = 'ppt_builder'),
    file_id uuid references powerpoint_file(id),
    config jsonb not null check (jsonb_typeof(config) = 'object'),
    primary key (organization_id, runtime_id),
    foreign key (runtime_id, capability_id) references runtime_capability(runtime_id, capability_id)
);
create trigger powerpoint_settings_organization before insert or update on organization_powerpoint_settings
    for each row execute function require_organization_space();

create function protect_powerpoint_settings() returns trigger language plpgsql as $$
begin
    if new.file_id is not null and not exists (
        select 1 from powerpoint_file where id = new.file_id
        and space_id = new.organization_id and runtime_id = new.runtime_id
        and agent_instance_id is null and status = 'stored' and effective
    ) then
        raise exception 'PowerPoint settings require the effective organization file' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger powerpoint_settings_file before insert or update on organization_powerpoint_settings
    for each row execute function protect_powerpoint_settings();

-- Corrections never silently move to a replacement deck. Retirement and promotion
-- run under the existing organization transaction lock.
create function retire_powerpoint_settings() returns trigger language plpgsql as $$
begin
    if new.status = 'retired' then
        delete from organization_powerpoint_settings where file_id = new.id;
    elsif new.effective and not old.effective and new.agent_instance_id is null then
        delete from organization_powerpoint_settings
            where organization_id = new.space_id and runtime_id = new.runtime_id and file_id is null;
    end if;
    return new;
end $$;
create trigger powerpoint_settings_retirement after update of status, effective on powerpoint_file
    for each row execute function retire_powerpoint_settings();
