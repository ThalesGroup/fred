-- Network writes outlive leases and process lifetimes. Never expire an uncertain write.
alter table document_upload add column put_pending boolean not null default false;
alter table document add column original_cleaned_at timestamptz;
alter table generation add column write_ids uuid[] not null default '{}';
alter table generation add column pending_writes uuid[] not null default '{}';
alter table generation add column pending_workspaces uuid[] not null default '{}';
alter table generation add constraint generation_pending_writes_known
    check (pending_writes <@ write_ids and pending_workspaces <@ write_ids);
-- Keep failed-upload manifests attached to the root until object cleanup is confirmed.
alter table document_upload add constraint document_upload_session_fkey
    foreign key (session_id, space_id) references session_metadata(session_id, space_id) on delete restrict;
create index document_upload_session on document_upload(session_id) where session_id is not null;
