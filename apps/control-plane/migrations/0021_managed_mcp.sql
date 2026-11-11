-- Two offer origins share the existing governance. A central source is not a pod:
-- it has no runtime_catalog row, ingress, templates or execution identity.
create table capability_source (
    source_id text primary key,
    origin text not null check (origin in ('pod', 'managed_mcp')),
    runtime_id text unique references runtime_catalog(runtime_id),
    check ((origin = 'pod' and runtime_id is not null and source_id = runtime_id)
        or (origin = 'managed_mcp' and runtime_id is null and source_id = '$mcp'))
);
alter table runtime_catalog add check (runtime_id <> '$mcp');
insert into capability_source select runtime_id, 'pod', runtime_id from runtime_catalog;
insert into capability_source values ('$mcp', 'managed_mcp', null);
create function register_pod_capability_source() returns trigger language plpgsql as $$
begin
    insert into capability_source values (new.runtime_id, 'pod', new.runtime_id);
    return new;
end $$;
create trigger runtime_catalog_source after insert on runtime_catalog
    for each row execute function register_pod_capability_source();

create table mcp_connection (
    id uuid primary key,
    logical_name text unique not null check (logical_name ~ '^[a-z0-9_-]{1,64}$'),
    display_name text not null check (length(btrim(display_name)) between 1 and 255),
    description text not null check (length(description) <= 2000),
    revision bigint not null default 1 check (revision > 0),
    configuration jsonb not null check (jsonb_typeof(configuration) = 'object'),
    enabled boolean not null default false,
    refresh_token uuid,
    observation_revision bigint,
    observation_state text not null default 'not_observed'
        check (observation_state in ('not_observed', 'available', 'unavailable')),
    error_code text,
    checked_at timestamptz,
    last_success_at timestamptz,
    observed_tools jsonb not null default '[]' check (jsonb_typeof(observed_tools) = 'array'),
    published_tools jsonb not null default '[]' check (jsonb_typeof(published_tools) = 'array'),
    published_revision bigint,
    updated_by text not null,
    updated_at timestamptz not null default clock_timestamp(),
    check (observation_revision is null or observation_revision <= revision),
    check (published_revision is null or published_revision <= revision)
);

alter table runtime_capability rename to capability_offer;
alter table capability_offer drop constraint runtime_capability_runtime_id_fkey;
alter table capability_offer rename column runtime_id to source_id;
alter table capability_offer add foreign key (source_id) references capability_source(source_id);
alter table capability_offer add column connection_id uuid unique references mcp_connection(id);
alter table capability_offer add check (
    (source_id = '$mcp' and connection_id is not null and capability_id = 'managed-mcp:' || connection_id::text)
    or (source_id <> '$mcp' and connection_id is null and capability_id not like 'managed-mcp:%')
);
-- Templates remain pod-owned even though their offers now have a common owner table.
alter table runtime_template_capability add foreign key (runtime_id) references runtime_catalog(runtime_id);
alter table organization_capability rename column runtime_id to source_id;
alter table space_capability_policy drop constraint space_capability_policy_runtime_id_fkey;
alter table space_capability_policy rename column runtime_id to source_id;
alter table space_capability_policy add foreign key (source_id) references capability_source(source_id);
alter table space_capability_permission rename column runtime_id to source_id;
-- No delete endpoint: disable instead. Offers and selections survive withdrawal.
-- A published tool inventory changes only through explicit platform publication.
