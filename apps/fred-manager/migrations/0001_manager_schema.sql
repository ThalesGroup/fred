-- Manager schema. Rights never live here: OpenFGA holds direct roles and the space tree.
-- Before the first production release this baseline is rewritten in place; a local
-- installation created from an earlier baseline is reset, never upgraded.

create type space_kind as enum ('organization', 'team', 'project');

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
create index space_deletion_due on space_deletion (last_visit nulls first, due_at, id) where status <> 'completed';
create index space_deletion_overlap on space_deletion (organization_id, target_parent_id) where status <> 'completed';

-- Identity and kind only. Sibling names and one personal space per organization are
-- enforced under the organization lock, since the tree lives in OpenFGA.
create table space (
    id             uuid primary key,
    kind           space_kind not null,
    name           text not null,
    personal_owner text,          -- set only for a personal space: a one-member team
    created_at     timestamptz not null default now(),
    deletion_id    uuid references space_deletion (id),
    check (personal_owner is null or kind = 'team')
);
create unique index space_organization_name on space (name) where kind = 'organization';
create index space_deletion_manifest on space (deletion_id, kind, id) where deletion_id is not null;

create table folder (
    id         uuid primary key,
    space_id   uuid not null references space (id),
    parent_id  uuid,
    name       text not null,
    path       text not null,     -- '/<id>/<id>/', ids only, copied into every chunk
    created_at timestamptz not null default now(),
    unique (id, space_id),
    foreign key (parent_id, space_id) references folder (id, space_id),
    unique nulls not distinct (space_id, parent_id, name)
);

create table document (
    id          uuid primary key,
    space_id    uuid not null references space (id),
    folder_id   uuid,             -- null means the space root
    name        text not null,
    mime        text not null,
    size        bigint not null,
    sha256      text not null,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    object_key  text not null unique,
    quota_owner uuid not null references space (id),
    foreign key (folder_id, space_id) references folder (id, space_id),
    unique nulls not distinct (space_id, folder_id, name),
    constraint document_size_valid check (size >= 0 and size <= 104857600),
    constraint document_digest_valid check (sha256 ~ '^[0-9a-f]{64}$')
);
create index document_quota_owner on document (quota_owner) include (size);

-- Placement is immutable: chunks and storage keys copy it. Only names change.
create function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.personal_owner) is distinct from (old.kind, old.personal_owner) then
        raise exception 'space placement is immutable';
    end if;
    return new;
end $$;

create function forbid_folder_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.parent_id, new.path) is distinct from (old.space_id, old.parent_id, old.path) then
        raise exception 'folder placement is immutable';
    end if;
    return new;
end $$;

create function forbid_document_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.folder_id) is distinct from (old.space_id, old.folder_id) then
        raise exception 'document placement is immutable';
    end if;
    return new;
end $$;

create trigger space_immutable before update on space for each row execute function forbid_space_move();
create trigger folder_immutable before update on folder for each row execute function forbid_folder_move();
create trigger document_immutable before update on document for each row execute function forbid_document_move();

-- Durable root-bootstrap marker, distinct from control-plane's `platformbootstrap`.
-- A claim (`completed_by`) is finished only once its grant is recorded: a null
-- `granted_at` means the OpenFGA write may not have happened, and only the claimant retries.
create table platform_bootstrap (
    singleton    boolean primary key default true check (singleton),
    completed_by text not null,
    completed_at timestamptz not null default now(),
    granted_at   timestamptz
);

-- Publishes a completely initialized OpenFGA store; never stores grants or permissions.
create table authorization_store (
    singleton boolean primary key default true check (singleton),
    configured_store text not null,
    source_store text not null,
    active_store text not null,
    model_id text not null
);

-- Consent belongs to an authenticated subject, independently of directory or space membership.
create table terms_acceptance (
    user_id text primary key,
    version text not null check (length(version) between 1 and 128),
    accepted_at timestamptz not null default now()
);

-- Namespace and inventory progress have a different lifetime from any upload.
create table document_storage (
    singleton boolean primary key default true check(singleton),
    namespace uuid not null,
    endpoint text not null,
    bucket text not null,
    prefix text not null,
    inventory_cursor text,
    inventory_bytes bigint not null default 0,
    orphan_bytes bigint not null default 0,
    inventory_completed_at timestamptz,
    lease_owner uuid,
    lease_until timestamptz
);

-- Historical target IDs deliberately survive failed uploads and target deletion.
create table document_upload (
    id uuid primary key,
    request_key uuid not null,
    actor text not null,
    organization_id uuid not null,
    space_id uuid not null,
    folder_id uuid not null,
    quota_owner uuid not null,
    name text not null,
    mime text not null,
    size bigint not null check(size >= 0 and size <= 104857600),
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    object_key text not null unique,
    status text not null check(status in ('pending', 'stored', 'failed')),
    document_id uuid unique references document(id),
    error_code text,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    completed_at timestamptz,
    acknowledged_at timestamptz,
    retry_of uuid unique references document_upload(id) on delete set null,
    successor_key uuid,
    cleanup_due_at timestamptz not null default now(),
    cleanup_attempts integer not null default 0,
    cleaned_at timestamptz,
    unique(actor, request_key),
    check((status = 'stored') = (document_id is not null)),
    check((status = 'pending') = (completed_at is null))
);
create unique index document_upload_active_name on document_upload(space_id, folder_id, name) where status = 'pending';
create index document_upload_active_quota on document_upload(quota_owner) include(size) where status = 'pending';
create index document_upload_receipts on document_upload(actor, space_id, created_at desc, request_key desc) where acknowledged_at is null;
create index document_upload_cleanup on document_upload(cleanup_due_at, id) where status = 'failed' and cleaned_at is null;
create index document_upload_expiration on document_upload(expires_at, id) where status = 'pending';

-- The organization lock orders application mutations; these checks also protect SQL callers.
create function protect_pending_document_uploads() returns trigger language plpgsql as $$
begin
    if TG_TABLE_NAME = 'folder' then
        if exists(select 1 from document_upload where folder_id = OLD.id and status = 'pending') then
            raise exception using errcode = '23503', message = 'folder has pending document uploads';
        end if;
    elsif exists(select 1 from document_upload where space_id = OLD.id and status = 'pending') then
        raise exception using errcode = '23503', message = 'space has pending document uploads';
    end if;
    return OLD;
end $$;
create trigger folder_pending_uploads before delete on folder for each row execute function protect_pending_document_uploads();
create trigger space_pending_uploads before delete on space for each row execute function protect_pending_document_uploads();
