-- PowerPoint originals belong to an organization or one space's agent instance.
-- This is persistence only: capability validation/preparation and runtime activation
-- remain mandatory before opening the user upload journey. No pod-derived data
-- is claimed to be purged by this registry.
alter table agent_instance add constraint agent_instance_id_space_unique
    unique (agent_instance_id, space_id);

create table powerpoint_file (
    id uuid primary key,
    request_key uuid not null,
    actor text not null,
    organization_id uuid not null,
    space_id uuid not null,
    agent_instance_id uuid,
    -- Live FKs protect placement; immutable provenance survives owner deletion.
    live_space_id uuid references space(id) on delete set null,
    live_agent_id uuid,
    foreign key (live_agent_id, live_space_id)
        references agent_instance(agent_instance_id, space_id) on delete set null (live_agent_id),
    quota_owner uuid not null,
    expected_file_id uuid,
    name text not null,
    mime text not null,
    size bigint not null check (size >= 0),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    object_key text not null unique,
    status text not null check (status in ('pending', 'stored', 'retired')),
    created_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz not null,
    published_at timestamptz,
    cleanup_due_at timestamptz not null,
    cleanup_attempts integer not null default 0 check (cleanup_attempts >= 0),
    cleaned_at timestamptz,
    error_code text,
    unique (actor, request_key),
    check (live_space_id is null or live_space_id = space_id),
    check (live_agent_id is null or live_agent_id = agent_instance_id),
    check (status = 'retired' or (live_space_id is not null and
        (agent_instance_id is null or live_agent_id is not null))),
    check (status <> 'stored' or published_at is not null),
    check (cleaned_at is null or status = 'retired')
);
create unique index powerpoint_organization_current on powerpoint_file(space_id)
    where status = 'stored' and agent_instance_id is null;
create unique index powerpoint_agent_current on powerpoint_file(agent_instance_id)
    where status = 'stored' and agent_instance_id is not null;
create index powerpoint_file_space on powerpoint_file(space_id);
create index powerpoint_file_agent on powerpoint_file(agent_instance_id) where agent_instance_id is not null;
create index powerpoint_file_live_agent on powerpoint_file(live_agent_id, live_space_id);
create index powerpoint_file_live_space on powerpoint_file(live_space_id);
create index powerpoint_file_quota on powerpoint_file(quota_owner) where status in ('pending', 'stored');
create index powerpoint_file_cleanup on powerpoint_file(cleanup_due_at, id) where status <> 'stored' and cleaned_at is null;

create function protect_powerpoint_file() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (select 1 from space s where s.id = new.space_id
            and s.organization_id = new.organization_id and s.deletion_id is null
            and (new.agent_instance_id is not null or s.kind = 'organization')) then
            raise exception 'invalid PowerPoint owner' using errcode = '23514';
        end if;
        if new.live_space_id is distinct from new.space_id
            or new.live_agent_id is distinct from new.agent_instance_id
            or new.status <> 'pending' then
            raise exception 'PowerPoint upload requires a live owner' using errcode = '23514';
        end if;
    else
        if (new.id, new.request_key, new.actor, new.organization_id, new.space_id,
            new.agent_instance_id, new.quota_owner, new.expected_file_id, new.name,
            new.mime, new.size, new.sha256, new.object_key, new.created_at, new.expires_at)
            is distinct from
           (old.id, old.request_key, old.actor, old.organization_id, old.space_id,
            old.agent_instance_id, old.quota_owner, old.expected_file_id, old.name,
            old.mime, old.size, old.sha256, old.object_key, old.created_at, old.expires_at)
            or (old.status = 'retired' and new.status <> 'retired')
            or (old.status = 'stored' and new.status = 'pending') then
            raise exception 'PowerPoint identity and terminal retirement are immutable' using errcode = '23514';
        end if;
    end if;
    return new;
end $$;
create trigger powerpoint_file_identity before insert or update on powerpoint_file
    for each row execute function protect_powerpoint_file();

create function retire_powerpoint_owner() returns trigger language plpgsql as $$
begin
    if tg_table_name = 'agent_instance' then
        update powerpoint_file set status = 'retired', cleanup_due_at = greatest(expires_at, clock_timestamp())
            where agent_instance_id = old.agent_instance_id and status <> 'retired';
    else
        update powerpoint_file set status = 'retired', cleanup_due_at = greatest(expires_at, clock_timestamp())
            where space_id = old.id and status <> 'retired';
    end if;
    return old;
end $$;
create trigger powerpoint_agent_retirement before delete on agent_instance
    for each row execute function retire_powerpoint_owner();
create trigger powerpoint_space_retirement before delete on space
    for each row execute function retire_powerpoint_owner();
