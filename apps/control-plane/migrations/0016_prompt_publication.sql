-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Publication exposes the current definition, never a second copy or version.
alter table prompt add column published boolean not null default false;

create function require_prompt_publication_team() returns trigger language plpgsql as $$
begin
    if new.published and not exists (
        select 1 from space where id = new.space_id and kind = 'team'
    ) then
        raise exception 'only team prompts can be published' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger prompt_publication_team before insert or update of published, space_id on prompt
    for each row execute function require_prompt_publication_team();

-- The organization is derived from placement. Walk each team's published UUIDs
-- without reading private definitions; UUID is an immutable keyset cursor.
create index prompt_published_space_id on prompt (space_id, prompt_id) where published;
