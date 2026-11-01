-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Categories belong to the prompt's space, never to a global taxonomy.
create table prompt_category (
    id uuid primary key,
    space_id uuid not null references space (id) on delete cascade,
    name varchar(120) not null check (btrim(name) <> ''),
    constraint prompt_category_space_name_key unique (space_id, name),
    constraint prompt_category_space_id_key unique (space_id, id)
);

alter table prompt add column category_id uuid;
alter table prompt add constraint prompt_category_same_space_fkey
    foreign key (space_id, category_id) references prompt_category (space_id, id);
-- NO ACTION blocks deleting a used category, while allowing the enclosing
-- space deletion to cascade to both prompts and categories in one statement.
create index prompt_space_category_idx on prompt (space_id, category_id);

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
        if (new.display_name, new.description, new.text, new.category_id)
            is distinct from (old.display_name, old.description, old.text, old.category_id) then
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;
