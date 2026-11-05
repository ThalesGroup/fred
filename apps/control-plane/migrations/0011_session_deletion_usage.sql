-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- A deletion receipt outlives its session and placement. Retain only the two
-- attribution facts absent from that receipt, so a previously admitted runtime
-- can report consumption after physical purge without asserting a person's identity.
-- Cleanup captures both in the same transaction that removes session_metadata.
alter table deletion
    add column session_user_id text,
    add column session_agent_instance_id uuid,
    add constraint deletion_session_usage_pair check (
        (session_user_id is null) = (session_agent_instance_id is null)
        and (session_user_id is null or target_kind = 'session')
    );
