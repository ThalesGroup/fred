-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh Weaver initialization only. One shared memory per agent instance: short
-- notes visible to every space member using that instance. Notes are never
-- edited in place: forgetting keeps the row as history, and an edit forgets the
-- note and remembers its new text in one transaction. The new note names the note
-- it revises and inherits the creation date of the first version, so an edited
-- note keeps its place in the active list. A note is revised at most once, by a
-- note of the same instance. Sessions are provenance only: notes outlive the
-- conversation that wrote them. The Control Plane caps active notes per instance
-- while holding the instance row.
set local lock_timeout = '5s';

create table agent_memory_note (
    note_id uuid primary key,
    space_id uuid not null,
    agent_instance_id uuid not null,
    content text not null check (char_length(btrim(content)) between 1 and 500),
    created_by text not null,
    -- Null when an editor added the note from the agent settings.
    created_session_id uuid,
    created_at timestamptz not null default clock_timestamp(),
    -- Transaction time, not clock_timestamp(): a row relying on both defaults would
    -- otherwise get an origin later than its created_at. The API sets both itself.
    origin_created_at timestamptz not null default now(),
    revises_note_id uuid,
    forgotten_by text,
    forgotten_session_id uuid,
    forgotten_at timestamptz,
    foreign key (agent_instance_id, space_id)
        references agent_instance (agent_instance_id, space_id) on delete cascade,
    constraint agent_memory_note_instance_note unique (note_id, agent_instance_id),
    constraint agent_memory_note_revises_once unique (revises_note_id),
    constraint agent_memory_note_revises_same_instance
        foreign key (revises_note_id, agent_instance_id)
        references agent_memory_note (note_id, agent_instance_id) on delete cascade,
    constraint agent_memory_note_origin_before_created
        check (origin_created_at <= created_at),
    check ((forgotten_by is null) = (forgotten_at is null)),
    check (forgotten_session_id is null or forgotten_at is not null)
);
-- Serves the active list in its displayed order, recent history and the cascade.
create index agent_memory_note_instance
    on agent_memory_note (agent_instance_id, forgotten_at, origin_created_at, created_at);
