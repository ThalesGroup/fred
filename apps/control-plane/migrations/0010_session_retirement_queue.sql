-- Space cleanup takes the next live conversations in placement/identity order.
-- Assigning a child receipt removes its entry, including blocked Python sessions,
-- so subsequent bounded visits do not scan the already-materialized manifest.
create index session_metadata_retirement_queue
    on session_metadata (space_id, session_id) where deletion_id is null;
