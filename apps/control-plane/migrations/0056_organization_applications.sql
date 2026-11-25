-- Fresh installations only: never invent an owner for an old global registration.
alter table application add column organization_id uuid not null references space(id) on delete cascade;
alter table application drop constraint application_logical_name_key;
alter table application add unique (organization_id, logical_name);
create trigger application_organization before insert or update of organization_id on application
    for each row execute function require_model_policy_organization();
comment on trigger application_organization on application is
    'assertion: consistency - application owner is an organization';

alter table capability_offer drop constraint capability_offer_application_id_fkey;
alter table capability_offer add foreign key (application_id) references application(id)
    on delete cascade deferrable initially deferred;

create or replace function preserve_application_identity() returns trigger language plpgsql as $$
begin
    if (new.id,new.logical_name,new.organization_id) is distinct from (old.id,old.logical_name,old.organization_id) then
        raise exception 'application identity and owner are immutable' using errcode = '23514', constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

-- Extend the existing owned-offer boundary; keep ownership on the source record.
alter function require_mcp_permission_scope() rename to require_owned_offer_permission_scope;
create or replace function require_owned_offer_permission_scope() returns trigger language plpgsql as $$
declare target uuid;
begin
    if new.source_id not in ('$mcp', '$applications') then return new; end if;
    if tg_table_name = 'organization_capability' then
        target := new.organization_id;
    else
        select organization_id into target from space where id = new.space_id;
    end if;
    if not exists (
        select 1 from capability_offer o
        left join mcp_connection c on c.id=o.connection_id
        left join space s on s.id=c.space_id
        left join application a on a.id=o.application_id
        where o.source_id=new.source_id and o.capability_id=new.capability_id
          and coalesce(a.organization_id,s.organization_id)=target
    ) then
        raise exception 'offer permission outside owning organization' using errcode = '23514', constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
alter trigger organization_mcp_scope on organization_capability rename to organization_owned_offer_scope;
alter trigger local_mcp_scope on space_capability_permission rename to local_owned_offer_scope;
comment on trigger organization_owned_offer_scope on organization_capability is
    'assertion: consistency - owned offer authorization stays in its organization';
comment on trigger local_owned_offer_scope on space_capability_permission is
    'assertion: consistency - local owned offer permission stays in its organization';

comment on trigger application_identity on application is
    'assertion: immutability - application UUID, logical name and owning organization';
