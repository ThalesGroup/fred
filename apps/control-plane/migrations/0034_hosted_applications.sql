-- Hosted applications share offer governance, never pod/template execution.
alter table capability_source drop constraint capability_source_origin_check;
alter table capability_source drop constraint capability_source_check;
alter table capability_source add check (origin in ('pod', 'managed_mcp', 'application'));
alter table capability_source add check (
    (origin = 'pod' and runtime_id is not null and source_id = runtime_id)
    or (origin = 'managed_mcp' and runtime_id is null and source_id = '$mcp')
    or (origin = 'application' and runtime_id is null and source_id = '$applications')
);
alter table runtime_catalog add check (runtime_id <> '$applications');
insert into capability_source values ('$applications', 'application', null);

-- Presentation/version and availability are owned only by capability_offer.
create table application (
    id uuid primary key,
    logical_name text not null unique check (logical_name ~ '^[a-z0-9_-]{1,64}$'),
    ui_base_url text not null check (length(ui_base_url) between 1 and 2048 and ui_base_url ~ '^https?://[^/?#@]+/[^?#]*$'),
    api_base_url text check (length(api_base_url) between 1 and 2048 and api_base_url ~ '^https?://[^/?#@]+/[^?#]*$'),
    entry_permission text not null default 'read' check (entry_permission in
        ('read','write','manage','run_evaluations','manage_evaluation_corpus','read_conversations_for_evaluation','read_usage')),
    revision bigint not null default 1 check (revision > 0),
    updated_by text not null,
    updated_at timestamptz not null default clock_timestamp(),
    source_id text not null default '$applications' check (source_id = '$applications'),
    capability_id text generated always as ('application:' || id::text) stored,
    foreign key(source_id, capability_id) references capability_offer(source_id, capability_id) deferrable initially deferred
);
alter table capability_offer add column application_id uuid unique references application(id) deferrable initially deferred;
alter table capability_offer add check (
    (source_id = '$applications' and application_id is not null and capability_id = 'application:' || application_id::text
        and descriptor->>'kind' is not distinct from 'application' and connection_id is null)
    or (source_id <> '$applications' and application_id is null and capability_id not like 'application:%')
);
create function preserve_application_identity() returns trigger language plpgsql as $$
begin
    if new.id <> old.id or new.logical_name <> old.logical_name then
        raise exception 'application identity is immutable' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger application_identity before update on application
    for each row execute function preserve_application_identity();
comment on trigger application_identity on application is
    'assertion: immutability - application UUID and logical name';
