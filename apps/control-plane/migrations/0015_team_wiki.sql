-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Editorial state belongs to its space, not to the file catalogue. Pending
-- proposals belong to a private conversation; published provenance is not ownership.
set local lock_timeout = '5s';

create table wiki_page (
    page_id uuid primary key,
    space_id uuid not null references space(id),
    slug text not null,
    title text not null check(char_length(title) between 1 and 300 and btrim(title) <> ''),
    kind text not null default 'page' check(kind in ('page','rules')),
    parent_page_id uuid,
    position integer not null default 0,
    current_revision_id uuid,
    needs_review boolean not null default false,
    updated_at timestamptz not null default now(),
    updated_by text not null,
    unique(page_id,space_id),
    unique(space_id,slug),
    foreign key(parent_page_id,space_id) references wiki_page(page_id,space_id),
    check(parent_page_id is distinct from page_id),
    check((kind='rules') = (slug='__rules__')),
    check(kind<>'rules' or parent_page_id is null)
);
create unique index wiki_sibling_title on wiki_page
    (space_id,parent_page_id,lower(btrim(regexp_replace(title,'[[:space:]]+',' ','g')))) nulls not distinct;
create index wiki_parent on wiki_page(parent_page_id);

create table wiki_revision (
    revision_id uuid primary key,
    space_id uuid not null references space(id),
    page_id uuid,
    content_md text not null check(char_length(content_md)<=100000),
    status text not null check(status in ('proposed','rejected','published','superseded')),
    base_revision_id uuid,
    author_user_id text not null,
    author_kind text not null check(author_kind in ('human','agent')),
    agent_instance_id uuid,
    -- No cascading session FK: published revisions survive their conversation.
    session_id uuid,
    proposed_title text check(char_length(proposed_title) between 1 and 300),
    proposed_parent_page_id uuid,
    created_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz,
    reviewed_at timestamptz,
    reviewed_by text,
    unique(revision_id,page_id,space_id),
    foreign key(page_id,space_id) references wiki_page(page_id,space_id) on delete cascade,
    foreign key(proposed_parent_page_id,space_id) references wiki_page(page_id,space_id)
        on delete set null (proposed_parent_page_id),
    check(status not in ('published','superseded') or page_id is not null),
    check(status not in ('proposed','rejected') or
        (session_id is not null and author_kind='agent' and expires_at is not null
         and (page_id is not null or proposed_title is not null))),
    check((author_kind='agent' and agent_instance_id is not null and session_id is not null)
       or (author_kind='human' and agent_instance_id is null and session_id is null)),
    check((reviewed_at is null) = (reviewed_by is null))
);
alter table wiki_page add constraint wiki_current_revision
    foreign key(current_revision_id,page_id,space_id)
    references wiki_revision(revision_id,page_id,space_id) deferrable initially deferred;
create index wiki_history on wiki_revision(space_id,page_id,created_at desc,revision_id desc)
    where status in ('published','superseded');
create index wiki_revision_page on wiki_revision(page_id);
create index wiki_revision_space on wiki_revision(space_id,revision_id);
create index wiki_private_session on wiki_revision(session_id,revision_id)
    where status in ('proposed','rejected');
create index wiki_expiry on wiki_revision(expires_at,revision_id) where status='proposed';

create function protect_wiki_revision() returns trigger language plpgsql as $$
begin
    if (new.revision_id,new.space_id,new.content_md,new.author_user_id,new.author_kind,
        new.agent_instance_id,new.session_id,new.created_at,new.expires_at,
        new.base_revision_id,new.proposed_title)
       is distinct from
       (old.revision_id,old.space_id,old.content_md,old.author_user_id,old.author_kind,
        old.agent_instance_id,old.session_id,old.created_at,old.expires_at,
        old.base_revision_id,old.proposed_title)
       or (old.page_id is not null and new.page_id is distinct from old.page_id)
       or (new.status<>old.status and not
           ((old.status='proposed' and new.status in ('published','rejected'))
             or (old.status='published' and new.status='superseded'))) then
        raise exception 'wiki revision content and provenance are immutable' using errcode='23514';
    end if;
    return new;
end $$;
create trigger wiki_revision_immutable before update on wiki_revision
    for each row execute function protect_wiki_revision();
