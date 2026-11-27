-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh Weaver initialization only. Editing a note stays forget + remember, done in
-- one transaction: the new note names the note it revises and inherits the creation
-- date of the first version, so an edited note keeps its place in the active list.
-- A note is revised at most once, by a note of the same instance. Revisions belong
-- to the instance: they go with it through the existing instance cascade.
set local lock_timeout = '5s';

alter table agent_memory_note
    add column revises_note_id uuid,
    add column origin_created_at timestamptz;

update agent_memory_note set origin_created_at = created_at;

alter table agent_memory_note
    alter column origin_created_at set not null,
    -- Transaction time, not clock_timestamp(): a row relying on both defaults would
    -- otherwise get an origin later than its created_at. The API sets both itself.
    alter column origin_created_at set default now(),
    add constraint agent_memory_note_origin_before_created
        check (origin_created_at <= created_at),
    add constraint agent_memory_note_instance_note unique (note_id, agent_instance_id),
    add constraint agent_memory_note_revises_once unique (revises_note_id),
    add constraint agent_memory_note_revises_same_instance
        foreign key (revises_note_id, agent_instance_id)
        references agent_memory_note (note_id, agent_instance_id) on delete cascade;

-- Serves the active list in its displayed order.
drop index agent_memory_note_instance;
create index agent_memory_note_instance
    on agent_memory_note (agent_instance_id, forgotten_at, origin_created_at, created_at);
