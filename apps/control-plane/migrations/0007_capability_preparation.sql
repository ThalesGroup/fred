-- Capability preparation is scoped to an installed library on one logical pod.
-- No document_processing rows/contracts are reused and no conversation runs here.
alter table powerpoint_file add column runtime_id text;
alter table powerpoint_file add column upload_ready boolean not null default false;
alter table powerpoint_file add column effective boolean not null default false;
update powerpoint_file set upload_ready=true where status='stored';
-- Existing agent attachments have canonical pod provenance; organization files
-- from the persistence-only increment remain unbound until an explicit replacement.
update powerpoint_file f set runtime_id=a.source_runtime_id from agent_instance a
    where f.agent_instance_id=a.agent_instance_id;
drop index powerpoint_organization_current;
create unique index powerpoint_organization_effective on powerpoint_file(space_id, runtime_id)
    where status = 'stored' and agent_instance_id is null and effective;
create unique index powerpoint_organization_candidate on powerpoint_file(space_id, runtime_id)
    where status = 'stored' and agent_instance_id is null and not effective;

-- A draft's immutable UUID is reserved before agent creation. Acceptance attaches
-- the live FK in the same transaction that creates the instance and its intention.
create or replace function protect_powerpoint_file() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (select 1 from space s where s.id = new.space_id
            and s.organization_id = new.organization_id and s.deletion_id is null
            and (new.agent_instance_id is not null or s.kind = 'organization')) then
            raise exception 'invalid PowerPoint owner' using errcode = '23514';
        end if;
        if new.live_space_id is distinct from new.space_id
            or (new.live_agent_id is not null and new.live_agent_id is distinct from new.agent_instance_id)
            or new.status <> 'pending' then
            raise exception 'PowerPoint upload requires a live space' using errcode = '23514';
        end if;
    else
        if (new.id, new.request_key, new.actor, new.organization_id, new.space_id,
            new.agent_instance_id, new.quota_owner, new.expected_file_id, new.name,
            new.mime, new.size, new.sha256, new.object_key, new.created_at, new.expires_at, new.runtime_id)
            is distinct from
           (old.id, old.request_key, old.actor, old.organization_id, old.space_id,
            old.agent_instance_id, old.quota_owner, old.expected_file_id, old.name,
            old.mime, old.size, old.sha256, old.object_key, old.created_at, old.expires_at, old.runtime_id)
            or (old.status = 'retired' and new.status <> 'retired')
            or (old.status = 'stored' and new.status = 'pending') then
            raise exception 'PowerPoint identity and terminal retirement are immutable' using errcode = '23514';
        end if;
    end if;
    return new;
end $$;
-- Replace only the named baseline check; drafts are pending, never stored or usable.
alter table powerpoint_file drop constraint powerpoint_file_check2;
alter table powerpoint_file add constraint powerpoint_file_live_owner check (
    status = 'retired' or (live_space_id is not null and
        (status = 'pending' or agent_instance_id is null or live_agent_id is not null)));

create table capability_preparation (
    id uuid primary key,
    file_id uuid not null references powerpoint_file(id),
    runtime_id text not null,
    capability_id text not null check (capability_id = 'ppt_builder'),
    space_id uuid not null,
    agent_instance_id uuid,
    configuration_revision bigint,
    config jsonb not null check (jsonb_typeof(config) = 'object'),
    state text not null default 'pending' check (state in ('pending','ready','failed','obsolete')),
    reference text,
    error text,
    created_at timestamptz not null default clock_timestamp(),
    deadline_at timestamptz not null default clock_timestamp() + interval '2 hours',
    workflow_id text not null unique,
    task_queue text not null,
    run_id text,
    delivered_at timestamptz,
    dispatch_owner uuid,
    dispatch_until timestamptz,
    delivery_due_at timestamptz not null default clock_timestamp(),
    cleaned_at timestamptz,
    check ((agent_instance_id is null) = (configuration_revision is null)),
    check (state <> 'ready' or reference is not null),
    check (length(reference) <= 256 and length(error) <= 2000)
);
create index capability_preparation_due on capability_preparation(delivery_due_at, id) where state = 'pending';
create index capability_preparation_cleanup on capability_preparation(runtime_id, id) where state = 'obsolete' and cleaned_at is null;
create index capability_preparation_file on capability_preparation(file_id);
create index capability_preparation_agent on capability_preparation(agent_instance_id);
alter table agent_instance add column preparation_id uuid references capability_preparation(id);
alter table agent_instance add column preparation_state text not null default 'ready' check (preparation_state in ('ready','pending','failed'));
alter table agent_instance add column preparation_error text;
update agent_instance a set preparation_state='failed',
    preparation_error='This stored PowerPoint file needs preparation. Save the agent to prepare it.'
    where exists(select 1 from powerpoint_file f where f.agent_instance_id=a.agent_instance_id and f.status='stored');

create function invalidate_capability_preparation() returns trigger language plpgsql as $$
begin
    if tg_table_name = 'powerpoint_file' then
        if new.status = 'retired' then
            update capability_preparation set state = 'obsolete' where file_id = new.id and state <> 'obsolete';
        end if;
        return new;
    end if;
    update capability_preparation set state = 'obsolete'
        where agent_instance_id = old.agent_instance_id and state <> 'obsolete';
    return old;
end $$;
create trigger capability_file_retirement after update of status on powerpoint_file
    for each row execute function invalidate_capability_preparation();
create trigger capability_agent_retirement before delete on agent_instance
    for each row execute function invalidate_capability_preparation();
