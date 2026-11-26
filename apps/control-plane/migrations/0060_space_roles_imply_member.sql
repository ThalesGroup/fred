-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Every space role is an addition to membership (#3661): owner, editor, analyst,
-- organization admin and organization observer all imply `member` of that space.
-- Control Plane writes and audits the implied grant; this trigger only refuses, at
-- commit, a (space, subject) holding another role without `member`. Platform roles
-- live in platform_role_grant and never imply membership.
set local lock_timeout = '5s';

-- One-off alignment of grants written before the rule.
insert into space_role_grant(space_id, subject, role)
select distinct space_id, subject, 'member' from space_role_grant where role <> 'member'
on conflict do nothing;

create function require_space_membership() returns trigger language plpgsql as $$
begin
    -- An update is checked on both its old and its new holder.
    if exists (
        select 1 from (
            select old.space_id, old.subject where TG_OP <> 'INSERT'
            union select new.space_id, new.subject where TG_OP <> 'DELETE'
        ) as holder(space_id, subject)
        where exists (select 1 from space_role_grant r where r.space_id = holder.space_id
                and r.subject = holder.subject and r.role <> 'member')
            and not exists (select 1 from space_role_grant r where r.space_id = holder.space_id
                and r.subject = holder.subject and r.role = 'member')
    ) then
        raise exception 'every space role requires membership' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return null;
end $$;

-- Deferred, so a transaction may write the role before its membership or remove
-- every role of a person in any order.
create constraint trigger space_role_membership after insert or update or delete on space_role_grant
    deferrable initially deferred
    for each row execute function require_space_membership();
comment on trigger space_role_membership on space_role_grant is
    'assertion: consistency - every space role holder is a member of that space';
