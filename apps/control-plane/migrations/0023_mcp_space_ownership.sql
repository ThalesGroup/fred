-- Fresh installations only. Existing unowned connections require reinstallation;
-- adding NOT NULL deliberately refuses to invent ownership for them.
alter table mcp_connection add column space_id uuid not null references space(id) on delete cascade;
alter table mcp_connection drop constraint mcp_connection_logical_name_key;
alter table mcp_connection add unique (space_id, logical_name);
drop index mcp_connection_tabular_service;
create unique index mcp_connection_tabular_service on mcp_connection(space_id)
    where configuration #>> '{authentication,kind}' = 'knowledge_flow_tabular';

-- Purging the owner also removes its projection and all offer permissions.
alter table capability_offer drop constraint capability_offer_connection_id_fkey;
alter table capability_offer add foreign key (connection_id) references mcp_connection(id) on delete cascade;
alter table organization_capability drop constraint organization_capability_runtime_id_capability_id_fkey;
alter table organization_capability add foreign key (source_id, capability_id)
    references capability_offer(source_id, capability_id) on delete cascade;
alter table space_capability_permission drop constraint space_capability_permission_runtime_id_capability_id_fkey;
alter table space_capability_permission add foreign key (source_id, capability_id)
    references capability_offer(source_id, capability_id) on delete cascade;

create function protect_mcp_owner() returns trigger language plpgsql as $$
begin
    if new.space_id is distinct from old.space_id then
        raise exception 'MCP owner is immutable' using errcode = '23514', constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger mcp_owner before update of space_id on mcp_connection
    for each row execute function protect_mcp_owner();

-- The connection is the only ownership fact. Grants cannot cross organizations,
-- including direct SQL writes; no scope is copied onto the offer projection.
create function require_mcp_permission_scope() returns trigger language plpgsql as $$
declare target uuid;
begin
    if new.source_id <> '$mcp' then return new; end if;
    if tg_table_name = 'organization_capability' then
        target := new.organization_id;
    else
        select organization_id into target from space where id = new.space_id;
    end if;
    if not exists (
        select 1 from capability_offer o join mcp_connection c on c.id=o.connection_id
        join space s on s.id=c.space_id
        where o.source_id=new.source_id and o.capability_id=new.capability_id
          and s.organization_id=target
    ) then
        raise exception 'MCP permission outside owning organization' using errcode = '23514', constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger organization_mcp_scope before insert or update on organization_capability
    for each row execute function require_mcp_permission_scope();
create trigger local_mcp_scope before insert or update on space_capability_permission
    for each row execute function require_mcp_permission_scope();

comment on trigger mcp_owner on mcp_connection is
    'assertion: immutability - MCP connection owner';
comment on trigger organization_mcp_scope on organization_capability is
    'assertion: consistency - MCP offer authorization stays in its owning organization';
comment on trigger local_mcp_scope on space_capability_permission is
    'assertion: consistency - local MCP permission stays in its owning organization';
comment on trigger runtime_catalog_source on runtime_catalog is
    'effect: register the pod capability source';
