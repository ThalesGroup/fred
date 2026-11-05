-- Rig owns the log format. The Control Plane owns its lifetime; retirement retains
-- it, and effective session purge removes it atomically with the product metadata.
create table embedded_agent_conversation (
    session_id uuid primary key references session_metadata (session_id) on delete cascade,
    log bytea not null
);
