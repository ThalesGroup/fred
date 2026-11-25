-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Keep assertion diagnostics usable by the invariant log contract. The guarded
-- conditions and SQLSTATE are unchanged; effective functions replace 0028-0034.
create or replace function require_team_join_link() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.space_id and kind = 'team') then
        raise exception 'Join links belong to teams' using errcode = '23514',
            constraint = 'team_join_link_space_kind', table = TG_TABLE_NAME;
    end if;
    return new;
end;
$$;

create or replace function require_team_avatar() returns trigger language plpgsql as $$
begin
    if new.space_id is not null and not exists (select 1 from space where id = new.space_id and kind = 'team') then
        raise exception 'Space avatars belong to teams' using errcode = '23514',
            constraint = 'avatar_space_kind', table = TG_TABLE_NAME;
    end if;
    return new;
end;
$$;

create or replace function require_local_model_policy() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id=new.space_id and kind in ('team','project')) then
        raise exception 'local model policy requires a team or project' using errcode = '23514',
            constraint = 'space_model_policy_kind', table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function preserve_application_identity() returns trigger language plpgsql as $$
begin
    if new.id <> old.id or new.logical_name <> old.logical_name then
        raise exception 'application identity is immutable' using errcode = '23514',
            constraint = 'application_identity', table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
