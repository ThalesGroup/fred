-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Storage only: the Control Plane still uses configured limits and live sums.
-- Populate these accounts only together with transactional counter maintenance.
create table storage_budget (
    space_id uuid not null references space(id) on delete cascade,
    scope text not null check (scope in ('local', 'organization_total')),
    limit_bytes bigint not null check (limit_bytes > 0),
    used_bytes bigint not null check (used_bytes >= 0),
    reserved_bytes bigint not null check (reserved_bytes >= 0),
    primary key (space_id, scope)
);
-- A limit can fall below existing usage; admission must then refuse new bytes.
-- No zero defaults: initialization must account for existing originals/uploads.
comment on table storage_budget is
    'Original-file usage and pending uploads only; excludes derived outputs and retired documents. Local and organization_total accounts overlap and must not be summed together.';

create function require_storage_budget_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
begin
    if TG_OP = 'UPDATE' then
        if (new.space_id, new.scope) is distinct from (old.space_id, old.scope) then
            raise exception 'storage budget identity is immutable' using errcode = '23514';
        end if;
        return new;
    end if;
    select kind into target_kind from space where id = new.space_id;
    if target_kind = 'project' then
        raise exception 'projects share their team storage budget' using errcode = '23514';
    end if;
    if new.scope = 'organization_total' and target_kind <> 'organization' then
        raise exception 'total storage budget requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger storage_budget_scope before insert or update on storage_budget
    for each row execute function require_storage_budget_scope();
