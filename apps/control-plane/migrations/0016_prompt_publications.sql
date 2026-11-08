-- Explicit publication destinations replace the source-derived boolean.
-- Weaver initializes fresh databases through the immutable migration chain.
create table prompt_publication (
    prompt_id uuid not null references prompt(prompt_id) on delete cascade,
    marketplace_space_id uuid not null references space(id) on delete cascade,
    published_by text not null check (btrim(published_by) <> ''),
    published_at timestamptz not null default clock_timestamp(),
    primary key (prompt_id, marketplace_space_id)
);
-- Catalogue pagination and destination-space cleanup start with this key.
create index prompt_publication_marketplace on prompt_publication (marketplace_space_id, prompt_id);

-- Only the source organization's marketplace is enabled. A platform audience
-- requires an explicit extension of the shared space/audience model and this
-- boundary; changing a source kind never changes its publication destination.
create function require_prompt_publication_destination() returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' then
        raise exception 'publication identity and attribution are immutable' using errcode = '23514';
    end if;
    if not exists (
        select 1 from prompt p join space s on s.id = p.space_id
        where p.prompt_id = new.prompt_id and s.organization_id = new.marketplace_space_id
    ) then
        raise exception 'prompt publication requires its organization marketplace' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger prompt_publication_destination before insert or update on prompt_publication
    for each row execute function require_prompt_publication_destination();

-- No second publication authority remains on the source definition.
drop trigger prompt_publication_team on prompt;
drop function require_prompt_publication_team();
alter table prompt drop column published;
