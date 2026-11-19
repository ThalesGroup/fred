-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- A definition belongs to one authenticated runtime; offers own its presentation.
set local lock_timeout = '5s';
create table kb_definition (
    id text primary key check (id ~ '^[a-z0-9][a-z0-9._-]{0,127}$'),
    runtime_id text not null references runtime_catalog(runtime_id),
    capability_id text generated always as ('knowledge-base:' || id) stored,
    unique(id,runtime_id),
    config_schema jsonb not null check (jsonb_typeof(config_schema)='object'),
    foreign key(runtime_id,capability_id) references capability_offer(source_id,capability_id)
);
create index kb_definition_runtime on kb_definition(runtime_id);
create table kb_instance (
    id uuid primary key,
    definition_id text not null references kb_definition(id),
    space_id uuid not null references space(id) on delete cascade,
    folder_id uuid not null unique,
    config jsonb not null check (jsonb_typeof(config)='object'),
    credential_refs jsonb not null check (jsonb_typeof(credential_refs)='object'),
    profile text not null,
    paused boolean not null default false,
    interval_seconds integer check (interval_seconds between 60 and 31536000),
    next_run_at timestamptz,
    created_by text not null,
    created_at timestamptz not null default clock_timestamp(),
    foreign key(folder_id,space_id) references folder(id,space_id) on delete cascade,
    unique(id,space_id,folder_id,definition_id)
);
create index kb_instance_space on kb_instance(space_id);
create index kb_instance_due on kb_instance(next_run_at,id) where not paused and interval_seconds is not null;
create table kb_run (
    id uuid primary key,
    instance_id uuid not null,
    runtime_id text not null references runtime_catalog(runtime_id),
    definition_id text not null references kb_definition(id),
    space_id uuid not null,
    folder_id uuid not null,
    config jsonb not null,
    credential_refs jsonb not null,
    profile text not null,
    state text not null default 'pending' check (state in ('pending','running','succeeded','failed')),
    request_key text not null check(length(request_key) between 1 and 128),
    requested_by text not null,
    created_at timestamptz not null default clock_timestamp(),
    deadline_at timestamptz not null default clock_timestamp()+interval '24 hours',
    completed_at timestamptz,
    error_code text,
    result jsonb,
    workflow_id text not null unique,
    task_queue text not null,
    temporal_run_id text,
    delivered_at timestamptz,
    delivery_due_at timestamptz not null default clock_timestamp(),
    dispatch_owner uuid,
    dispatch_until timestamptz,
    foreign key(definition_id,runtime_id) references kb_definition(id,runtime_id),
    foreign key(instance_id,space_id,folder_id,definition_id) references kb_instance(id,space_id,folder_id,definition_id) on delete cascade,
    unique(instance_id,request_key),
    check ((state in ('succeeded','failed'))=(completed_at is not null))
);
create unique index kb_run_active on kb_run(instance_id) where state in ('pending','running');
create index kb_run_dispatch on kb_run(delivery_due_at,id) where state in ('pending','running');
create index kb_run_definition on kb_run(definition_id);
create index kb_run_runtime on kb_run(runtime_id);
create function protect_kb_identity() returns trigger language plpgsql as $$
begin
    if tg_table_name='kb_definition' then
        if (new.id,new.runtime_id) is distinct from (old.id,old.runtime_id) then
            raise exception 'knowledge base definition ownership is immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    elsif tg_table_name='kb_instance' then
        if (new.id,new.definition_id,new.space_id,new.folder_id,new.config,new.credential_refs,new.profile,new.created_at,new.created_by)
            is distinct from (old.id,old.definition_id,old.space_id,old.folder_id,old.config,old.credential_refs,old.profile,old.created_at,old.created_by) then
            raise exception 'knowledge base source and placement are immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    else
        if (new.id,new.instance_id,new.runtime_id,new.definition_id,new.space_id,new.folder_id,new.config,new.credential_refs,new.profile,new.request_key,new.requested_by,new.deadline_at,new.workflow_id,new.task_queue,new.created_at)
            is distinct from (old.id,old.instance_id,old.runtime_id,old.definition_id,old.space_id,old.folder_id,old.config,old.credential_refs,old.profile,old.request_key,old.requested_by,old.deadline_at,old.workflow_id,old.task_queue,old.created_at)
            or (old.state='running' and new.state='pending')
            or (old.state in ('succeeded','failed') and (new.state,new.completed_at,new.error_code,new.result) is distinct from (old.state,old.completed_at,old.error_code,old.result)) then
            raise exception 'knowledge base run identity and outcome are immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;
create trigger kb_definition_identity before update on kb_definition for each row execute function protect_kb_identity();
comment on trigger kb_definition_identity on kb_definition is 'assertion: immutability - authenticated definition owner';
create trigger kb_instance_identity before update on kb_instance for each row execute function protect_kb_identity();
comment on trigger kb_instance_identity on kb_instance is 'assertion: immutability - managed mirror source and placement';
create trigger kb_run_identity before update on kb_run for each row execute function protect_kb_identity();
comment on trigger kb_run_identity on kb_run is 'assertion: immutability - admitted run scope and terminal outcome';

create function require_kb_folder() returns trigger language plpgsql as $$
begin
    if not exists(select 1 from folder where id=new.folder_id and space_id=new.space_id and parent_id is null and deletion_id is null)
       or exists(select 1 from document where folder_id=new.folder_id)
       or exists(select 1 from folder where parent_id=new.folder_id) then
        raise exception 'knowledge base requires a dedicated empty root folder' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger kb_instance_folder before insert on kb_instance for each row execute function require_kb_folder();
comment on trigger kb_instance_folder on kb_instance is 'assertion: consistency - managed mirror owns an empty dedicated root folder';
