-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

alter table prompt add column tags text[] not null default '{}'
    check (cardinality(tags) <= 20 and array_position(tags, null) is null);
-- Authored prompts require content from creation onward.
alter table prompt add constraint prompt_nonblank_text check (text ~ '[^[:space:]]');

-- Like users_preferences, the verified subject is text. user_identity is a
-- best-effort directory cache, not the account authority and cannot own this FK.
-- Account erasure must purge this table alongside users_preferences. Access
-- revocation retains the preference; authorized reads never expose it without access.
create table prompt_favorite (
    user_id text not null check (btrim(user_id) <> ''),
    prompt_id uuid not null references prompt(prompt_id) on delete cascade,
    primary key (user_id, prompt_id)
);
create index prompt_favorite_prompt_idx on prompt_favorite(prompt_id);

create or replace function protect_prompt_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if (new.prompt_id, new.space_id, new.logical_name, new.created_at, new.created_by)
            is distinct from
            (old.prompt_id, old.space_id, old.logical_name, old.created_at, old.created_by) then
            raise exception 'prompt identity and creation metadata are immutable' using errcode = '23514';
        end if;
        if (new.display_name, new.description, new.text, new.category_id, new.tags)
            is distinct from (old.display_name, old.description, old.text, old.category_id, old.tags) then
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;
