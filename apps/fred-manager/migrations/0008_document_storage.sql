-- A metadata-only PoC cannot claim that originals exist after this upgrade.
do $$ begin
    if exists(select 1 from document) then
        raise exception 'document storage upgrade requires an empty document registry; migrate originals or explicitly reset the disposable PoC first';
    end if;
end $$;

alter table document add column object_key text not null unique;
alter table document add column quota_owner uuid not null references space(id);
alter table document add constraint document_size_valid check (size >= 0 and size <= 104857600);
alter table document add constraint document_digest_valid check (sha256 ~ '^[0-9a-f]{64}$');
create index document_quota_owner on document(quota_owner) include(size);

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
