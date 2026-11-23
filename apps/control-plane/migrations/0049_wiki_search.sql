-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Rebuildable projection, never publication or authorization authority.
set local lock_timeout = '5s';
create table wiki_page_index (
    page_id uuid primary key,
    space_id uuid not null,
    kind text generated always as ('page'::text) stored,
    revision_id uuid not null,
    title text not null,
    index_version integer not null check(index_version > 0),
    page_type text not null,
    description text,
    read_when text,
    aliases text[] not null,
    tags text[] not null,
    body text not null,
    search_vector tsvector not null,
    foreign key(page_id,space_id,kind) references wiki_page(page_id,space_id,kind) on delete cascade
);
create index wiki_search_vector on wiki_page_index using gin(search_vector);
create index wiki_search_tags on wiki_page_index using gin(tags);
create index wiki_search_space_type on wiki_page_index(space_id,page_type);
