-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Extend the existing avatar lifecycle, namespace and sweeper to team photos.
alter table user_avatar rename to avatar;
alter table avatar alter column user_id drop not null;
alter table avatar add column space_id uuid references space(id) on delete set null;
alter table avatar add constraint avatar_owner check (
    (user_id is not null and space_id is null) or
    (user_id is null and space_id is not null) or
    (user_id is null and space_id is null and status = 'retired')
);
create unique index avatar_space_active on avatar(space_id) where status = 'active';
create unique index avatar_space_pending on avatar(space_id) where status = 'pending';
create index avatar_space on avatar(space_id) where space_id is not null;

-- Keep the cleanup journal after space purge, including uncertain pending PUTs.
create function retire_space_avatar() returns trigger language plpgsql as $$
begin
    update avatar set status = 'retired' where space_id = old.id;
    return old;
end;
$$;
create trigger space_avatar_retirement before delete on space
    for each row execute function retire_space_avatar();
comment on trigger space_avatar_retirement on space is
    'effect: retire team avatars while retaining their durable object cleanup journal';

create function require_team_avatar() returns trigger language plpgsql as $$
begin
    if new.space_id is not null and not exists (select 1 from space where id = new.space_id and kind = 'team') then
        raise exception 'Space avatars belong to teams' using errcode = '23514', constraint = 'avatar_space_kind';
    end if;
    return new;
end;
$$;
create trigger avatar_space_kind before insert or update of space_id on avatar
    for each row execute function require_team_avatar();
comment on trigger avatar_space_kind on avatar is
    'assertion: consistency - collective avatars belong only to teams; personal avatars belong to subjects';
