-- Operational receipts outlive their target; canonical placement and roles remain in FGA.
create table space_deletion (
    id uuid primary key,
    target_id uuid not null unique,
    target_kind space_kind not null,
    target_parent_id uuid,
    organization_id uuid not null,
    actor_subject text not null,
    requested_at timestamptz not null,
    due_at timestamptz not null,
    mode text not null check (mode in ('deferred_delete', 'immediate_delete')),
    rule_id text,
    status text not null default 'queued' check (status in ('queued','running','retrying','blocked','completed')),
    last_visit timestamptz,
    completed_at timestamptz,
    error_code text,
    folders_deleted bigint not null default 0 check (folders_deleted >= 0),
    spaces_deleted bigint not null default 0 check (spaces_deleted >= 0),
    check (due_at >= requested_at),
    check ((status = 'completed') = (completed_at is not null)),
    check ((target_kind = 'organization') = (target_parent_id is null))
);
alter table space add column deletion_id uuid references space_deletion(id);
create index space_deletion_manifest on space (deletion_id, kind, id) where deletion_id is not null;
create index space_deletion_due on space_deletion (last_visit nulls first, due_at, id) where status <> 'completed';
create index space_deletion_overlap on space_deletion (organization_id, target_parent_id) where status <> 'completed';
