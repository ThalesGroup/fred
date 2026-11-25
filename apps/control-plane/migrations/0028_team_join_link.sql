-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- A shareable link admits organization members as permanent team members.
-- Its expiration limits redemption, never the lifetime of an existing role.
create table team_join_link (
    space_id uuid primary key references space(id) on delete cascade,
    token uuid not null unique,
    created_by text not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    check (expires_at > created_at)
);

create function require_team_join_link() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.space_id and kind = 'team') then
        raise exception 'Join links belong to teams' using errcode = '23514', constraint = 'team_join_link_space_kind';
    end if;
    return new;
end;
$$;
create trigger team_join_link_space before insert or update of space_id on team_join_link
    for each row execute function require_team_join_link();
comment on trigger team_join_link_space on team_join_link is
    'assertion: consistency - shareable membership links belong only to teams';
