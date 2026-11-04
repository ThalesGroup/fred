-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Runtime owns its payload tables. The shared PostgreSQL root owns their lifetime.
-- REFERENCES permits runtime migrations to bind them without reading or mutating
-- Control Plane data. Bootstrap also preserves this narrow schema access on replay.
grant usage on schema control_plane to fred_runtime;
grant references (session_id) on session_metadata to fred_runtime;

-- A purged UUID must never become a new parent for an old admitted writer.
-- Deletion receipts intentionally survive their target and are never recycled.
create function forbid_session_recreation() returns trigger language plpgsql as $$
begin
    if exists (select 1 from deletion where target_kind = 'session' and target_id = new.session_id) then
        raise exception 'retired conversation identifier cannot be reused' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger session_identity_not_reused before insert on session_metadata
    for each row execute function forbid_session_recreation();
