-- Organization diagnostics are delegated by the organization admin.
-- This role grants neither business content access nor technical settings writes.
alter table space_role_grant drop constraint space_role_grant_role_check;
alter table space_role_grant add constraint space_role_grant_role_check
    check (role in ('member', 'editor', 'owner', 'analyst', 'organization_admin', 'organization_observer'));

create or replace function require_space_role_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
    target_owner text;
begin
    select kind, personal_owner into target_kind, target_owner from space where id = new.space_id;
    if target_kind = 'personal' and target_owner <> new.subject then
        raise exception 'personal space roles require its owner' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.role in ('organization_admin', 'organization_observer') and target_kind <> 'organization' then
        raise exception 'organization governance role requires an organization' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
