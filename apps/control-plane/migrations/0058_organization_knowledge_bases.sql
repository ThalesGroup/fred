-- Dedicated collectors are organization-owned services, not Agent Pods.
create table kb_service (
    runtime_id text primary key check(runtime_id ~ '^[a-zA-Z0-9_-]{1,64}$'),
    organization_id uuid not null references space(id) on delete cascade,
    issuer text not null,
    client_id text not null,
    audience text not null,
    credential_bindings text[] not null default '{}',
    revision bigint not null default 1 check(revision>0),
    unique(issuer,client_id)
);
create index kb_service_organization on kb_service(organization_id);
create trigger kb_service_organization before insert or update of organization_id on kb_service
    for each row execute function require_model_policy_organization();
comment on trigger kb_service_organization on kb_service is 'assertion: consistency - collector owner is an organization';

alter table capability_source drop constraint capability_source_origin_check;
alter table capability_source drop constraint capability_source_check;
alter table capability_source add column kb_service_id text unique references kb_service(runtime_id) on delete cascade;
alter table capability_source add check (origin in ('pod','managed_mcp','application','knowledge_base'));
alter table capability_source add check (
    (origin='pod' and runtime_id is not null and source_id=runtime_id and kb_service_id is null)
    or (origin='managed_mcp' and runtime_id is null and source_id='$mcp' and kb_service_id is null)
    or (origin='application' and runtime_id is null and source_id='$applications' and kb_service_id is null)
    or (origin='knowledge_base' and runtime_id is null and source_id=kb_service_id)
);
-- Name columns explicitly now that collector provenance is part of the source.
create or replace function register_pod_capability_source() returns trigger language plpgsql as $$
begin
    insert into capability_source(source_id,origin,runtime_id) values(new.runtime_id,'pod',new.runtime_id);
    return new;
end $$;
alter table capability_offer drop constraint capability_offer_source_id_fkey;
alter table capability_offer add foreign key(source_id) references capability_source(source_id) on delete cascade;
alter table space_capability_policy drop constraint space_capability_policy_source_id_fkey;
alter table space_capability_policy add foreign key(source_id) references capability_source(source_id) on delete cascade;

alter table kb_definition drop constraint kb_definition_runtime_id_fkey;
alter table kb_definition add foreign key(runtime_id) references kb_service(runtime_id) on delete cascade;
alter table kb_definition add column logical_name text not null;
alter table kb_definition add unique(runtime_id,logical_name);
alter table kb_definition drop constraint kb_definition_runtime_id_capability_id_fkey;
alter table kb_definition add foreign key(runtime_id,capability_id) references capability_offer(source_id,capability_id) on delete cascade deferrable initially deferred;
alter table kb_run drop constraint kb_run_runtime_id_fkey;
alter table kb_run add foreign key(runtime_id) references kb_service(runtime_id) on delete cascade;

create function protect_kb_service() returns trigger language plpgsql as $$
begin
    if (new.runtime_id,new.organization_id,new.issuer,new.client_id,new.audience) is distinct from
       (old.runtime_id,old.organization_id,old.issuer,old.client_id,old.audience) then
        raise exception 'collector identity and organization are immutable' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger kb_service_identity before update on kb_service for each row execute function protect_kb_service();
comment on trigger kb_service_identity on kb_service is 'assertion: immutability - dedicated collector identity and organization';

create or replace function require_owned_offer_permission_scope() returns trigger language plpgsql as $$
declare target uuid; owner uuid;
begin
    if tg_table_name='organization_capability' then target:=new.organization_id;
    else select organization_id into target from space where id=new.space_id; end if;
    select coalesce(a.organization_id,s.organization_id,k.organization_id) into owner
    from capability_offer o
    left join application a on a.id=o.application_id
    left join mcp_connection c on c.id=o.connection_id
    left join space s on s.id=c.space_id
    left join kb_service k on k.runtime_id=o.source_id
    where o.source_id=new.source_id and o.capability_id=new.capability_id;
    if owner is not null and owner<>target then
        raise exception 'offer permission outside owning organization' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create function require_kb_instance_organization() returns trigger language plpgsql as $$
begin
    if not exists(select 1 from kb_definition d join kb_service k on k.runtime_id=d.runtime_id
        join space s on s.organization_id=k.organization_id where d.id=new.definition_id and s.id=new.space_id) then
        raise exception 'collector outside destination organization' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger kb_instance_organization before insert on kb_instance for each row execute function require_kb_instance_organization();
comment on trigger kb_instance_organization on kb_instance is 'assertion: consistency - collection stays in its collector organization';

create or replace function protect_kb_identity() returns trigger language plpgsql as $$
begin
    if tg_table_name='kb_definition' then
        if (new.id,new.runtime_id,new.logical_name) is distinct from (old.id,old.runtime_id,old.logical_name) then
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
