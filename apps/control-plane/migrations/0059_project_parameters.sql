-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Fresh Weaver initialization only. Projects carry the same parameters as teams.
-- A project's visibility and open joining mode address members of its parent team.
alter table space drop constraint space_team_description;
alter table space add constraint space_team_description check (
    description is null or (
        kind in ('team', 'project') and char_length(description) between 20 and 500
        and description = btrim(description)
    )
);
alter table space drop constraint space_team_discovery;
alter table space add constraint space_team_discovery check (
    visibility in ('visible', 'hidden') and joining_mode in ('invite_only', 'open')
    and (kind in ('team', 'project') or (visibility = 'hidden' and joining_mode = 'invite_only'))
);
alter table space drop constraint team_conversation_retention;
alter table space add constraint team_conversation_retention check (
    conversation_retention_seconds is null or
    (kind in ('team', 'project') and conversation_retention_seconds >= 0)
);

create or replace function require_team_avatar() returns trigger language plpgsql as $$
begin
    if new.space_id is not null and not exists (
        select 1 from space where id = new.space_id and kind in ('team', 'project')
    ) then
        raise exception 'Space avatars belong to teams or projects' using errcode = '23514',
            constraint = 'avatar_space_kind', table = TG_TABLE_NAME;
    end if;
    return new;
end;
$$;
comment on trigger avatar_space_kind on avatar is
    'assertion: consistency - collective avatars belong only to teams and projects; personal avatars belong to subjects';
