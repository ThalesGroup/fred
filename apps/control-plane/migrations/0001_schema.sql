-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Control Plane schema. Rights never live here: OpenFGA holds direct roles and the links
-- that evaluate inherited permissions; SQL records each space's immutable placement.

create type space_kind as enum ('organization', 'team', 'project', 'personal');

-- Operational receipts outlive their target; canonical placement and roles remain in FGA.
-- Session IDs are client-chosen, so a target is identified by its kind and its ID.
create table deletion (
    id uuid primary key,
    target_id uuid not null,
    target_kind text not null check (target_kind in ('organization', 'team', 'project', 'document', 'session')),
    target_parent_id uuid,
    organization_id uuid not null,
    actor_subject text not null,
    requested_at timestamptz not null,
    due_at timestamptz not null,
    rule_id text,
    status text not null default 'queued' check (status in ('queued','running','retrying','blocked','completed')),
    last_visit timestamptz,
    completed_at timestamptz,
    error_code text,
    folders_deleted bigint not null default 0 check (folders_deleted >= 0),
    spaces_deleted bigint not null default 0 check (spaces_deleted >= 0),
    documents_deleted bigint not null default 0 check (documents_deleted >= 0),
    constraint deletion_target_key unique (target_kind, target_id),
    check (due_at >= requested_at),
    check ((status = 'completed') = (completed_at is not null)),
    constraint deletion_target_parent_check check ((target_kind = 'organization') = (target_parent_id is null))
);
create index deletion_due on deletion (last_visit nulls first, due_at, id) where status <> 'completed';
create index deletion_overlap on deletion (organization_id, target_parent_id) where status <> 'completed';

-- Sibling names and one personal space per organization are enforced under the
-- organization lock. Placement is written once, before the matching OpenFGA links.
create table space (
    id              uuid primary key,
    kind            space_kind not null,
    name            text not null,
    personal_owner  text,
    created_at      timestamptz not null default now(),
    deletion_id     uuid references deletion (id),
    organization_id uuid not null references space (id),
    parent_id       uuid references space (id),
    constraint space_personal_identity check (
        (kind = 'personal') = (personal_owner is not null)
        and (kind <> 'personal' or parent_id is null)
    )
);
comment on column space.personal_owner is 'Owner identity of a personal space; null for other space kinds';
create unique index space_organization_name on space (name) where kind = 'organization';
create index space_deletion_manifest on space (deletion_id, kind, id) where deletion_id is not null;
create index space_organization on space (organization_id);
create index space_parent on space (parent_id);
-- One active personal space per owner and organization; retired rows do not count.
create unique index space_personal_owner on space (organization_id, personal_owner)
    where personal_owner is not null and deletion_id is null;

-- Retired folders and documents are absent from reads and name uniqueness.
create table folder (
    id          uuid primary key,
    space_id    uuid not null references space (id),
    parent_id   uuid,
    name        text not null,
    path        text not null,     -- '/<id>/<id>/', ids only, copied into every chunk
    created_at  timestamptz not null default now(),
    deletion_id uuid references deletion (id),
    unique (id, space_id),
    foreign key (parent_id, space_id) references folder (id, space_id)
);
create index folder_deletion_manifest on folder (deletion_id) where deletion_id is not null;
create unique index folder_space_id_parent_id_name_key on folder (space_id, parent_id, name)
    nulls not distinct where deletion_id is null;

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
    retrievable boolean not null default false,
    -- The last search-inclusion command; KF confirms it after the claim/applied phases.
    retrieval_id        uuid,
    retrieval_actor     text,
    retrieval_target    boolean,
    retrieval_phase     text check (retrieval_phase in ('ready', 'writing', 'applied')),
    retrieval_confirmed boolean,
    retrievable_pending boolean generated always as
        (retrieval_id is not null and not retrieval_confirmed) stored,
    published_generation uuid,    -- the official processing result; foreign key below
    purged_at   timestamptz,      -- retired document whose vectors and outputs are gone
    deletion_id uuid references deletion (id),
    foreign key (folder_id, space_id) references folder (id, space_id),
    constraint document_size_valid check (size >= 0 and size <= 104857600),
    constraint document_digest_valid check (sha256 ~ '^[0-9a-f]{64}$'),
    constraint document_retrieval_command check (
        num_nulls(retrieval_id, retrieval_actor, retrieval_target, retrieval_phase, retrieval_confirmed) in (0, 5)
    ),
    check (purged_at is null or deletion_id is not null)
);
create index document_quota_owner on document (quota_owner) include (size);
create index document_deletion_manifest on document (deletion_id) where deletion_id is not null;
create index document_purge on document (id) where deletion_id is not null and purged_at is null;
create unique index document_space_id_folder_id_name_key on document (space_id, folder_id, name)
    nulls not distinct where deletion_id is null;

-- Placement is immutable: chunks and storage keys copy it. Only names change.
create function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.personal_owner, new.organization_id, new.parent_id)
        is distinct from (old.kind, old.personal_owner, old.organization_id, old.parent_id) then
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

-- Durable root-bootstrap marker. A claim (`completed_by`) is finished only once its
-- grant is recorded: a null `granted_at` means the OpenFGA write may not have happened,
-- and only the claimant retries.
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

-- Profiles observed after authentication. No grants or membership live here.
-- Usernames are not unique at the provider.
create table user_identity (
    id uuid primary key,
    username text not null,
    email text,
    first_name text,
    last_name text,
    last_seen_at timestamptz not null default now()
);
create index user_identity_username on user_identity (username, id);
-- Candidate search matches a case-insensitive prefix of each profile field.
create index user_identity_username_prefix on user_identity (lower(username) text_pattern_ops);
create index user_identity_email_prefix on user_identity (lower(email) text_pattern_ops);
create index user_identity_first_name_prefix on user_identity (lower(first_name) text_pattern_ops);
create index user_identity_last_name_prefix on user_identity (lower(last_name) text_pattern_ops);

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
    derived_endpoint text,
    derived_bucket text,
    derived_prefix text,
    inventory_completed_at timestamptz,
    lease_owner uuid,
    lease_until timestamptz
);

-- Historical target IDs deliberately survive failed uploads and target deletion.
-- A stored upload's id is its document's id.
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
    error_code text,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    completed_at timestamptz,
    acknowledged_at timestamptz,
    retry_of uuid unique references document_upload(id) on delete set null,
    successor_key uuid,
    processing_profile text check(processing_profile in ('fast','medium','rich')),
    cleanup_due_at timestamptz not null default now(),
    cleanup_attempts integer not null default 0,
    cleaned_at timestamptz,
    unique(actor, request_key),
    check((status = 'pending') = (completed_at is null))
);
create unique index document_upload_active_name on document_upload(space_id, folder_id, name) where status = 'pending';
create index document_upload_active_quota on document_upload(quota_owner) include(size) where status = 'pending';
create index document_upload_receipts on document_upload(actor, space_id, created_at desc, request_key desc) where acknowledged_at is null;
create index document_upload_cleanup on document_upload(cleanup_due_at, id) where status = 'failed' and cleaned_at is null;
create index document_upload_expiration on document_upload(expires_at, id) where status = 'pending';

-- Processing requests and their Temporal outbox. Results live in `generation`; the
-- document's space remains the only authorization object.
create table document_processing (
    id uuid primary key,
    request_key uuid not null,
    actor text not null,
    document_id uuid not null references document(id),
    profile text not null check(profile in ('fast','medium','rich')),
    status text not null default 'pending' check(status in ('pending','running','succeeded','failed')),
    stage text not null default 'queued' check(stage in ('queued','preparation','extraction','indexing','done')),
    revision bigint not null default 0,
    workflow_id text not null unique,
    submission jsonb not null,
    run_id text,
    first_dispatch_at timestamptz,
    delivered_at timestamptz,
    delivery_due_at timestamptz not null default now(),
    delivery_attempts integer not null default 0,
    dispatch_owner uuid,
    dispatch_until timestamptz,
    created_at timestamptz not null default now(),
    deadline_at timestamptz not null,
    completed_at timestamptz,
    error_code text,
    retry_of uuid unique references document_processing(id),
    profile_settings jsonb not null,
    -- Stage leases, copied from the KF submission policy at admission.
    preparation_seconds integer not null check(preparation_seconds>0),
    extraction_seconds integer not null check(extraction_seconds>0),
    indexing_seconds integer not null check(indexing_seconds>0),
    unique(actor,request_key),
    check((status in ('succeeded','failed')) = (completed_at is not null))
);
create unique index document_processing_active on document_processing(document_id) where status in ('pending','running');
create unique index document_processing_success on document_processing(document_id) where status='succeeded';
create index document_processing_history on document_processing(document_id,created_at desc,id desc);
create index document_processing_delivery on document_processing(delivery_due_at,id) where status in ('pending','running');

create function protect_processing_identity() returns trigger language plpgsql as $$
begin
    if (new.actor,new.request_key,new.document_id,new.profile,new.workflow_id,new.retry_of,new.submission,new.profile_settings,new.preparation_seconds,new.extraction_seconds,new.indexing_seconds)
        is distinct from (old.actor,old.request_key,old.document_id,old.profile,old.workflow_id,old.retry_of,old.submission,old.profile_settings,old.preparation_seconds,old.extraction_seconds,old.indexing_seconds) then
        raise exception 'processing identity is immutable';
    end if;
    if old.status in ('succeeded','failed') and (new.status,new.stage,new.completed_at,new.error_code) is distinct from (old.status,old.stage,old.completed_at,old.error_code) then
        raise exception 'processing outcome is final';
    end if;
    return new;
end $$;
create trigger document_processing_identity before update on document_processing for each row execute function protect_processing_identity();

-- One row per stage attempt. Its outputs live under `prefix`, computed once at creation;
-- readers never recompute a location. `chunks` fences the vector ordinals it may write.
create table generation (
    id uuid primary key,
    processing_id uuid not null references document_processing(id) on delete cascade,
    stage text not null check(stage in ('preparation','extraction','indexing')),
    execution_id uuid not null,
    activity_id uuid not null,
    attempt integer not null check(attempt>0),
    created_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz not null,
    prefix text not null,
    committed_at timestamptz,
    chunks integer not null default 0 check(chunks>=0),
    vector_ordinals integer[] check((committed_at is null) = (vector_ordinals is null)),
    rows bigint check(rows>=0),
    cleanup_cursor integer not null default 0 check(cleanup_cursor>=0),
    cleaned_at timestamptz
);
create index generation_processing on generation(processing_id,created_at,id);
create index generation_cleanup on generation(expires_at,id) where cleaned_at is null;

-- Committed outputs; preview checks the size, KF and publication check the digest.
create table artifact (
    generation_id uuid not null references generation(id) on delete cascade,
    path text not null,
    size bigint not null check(size>=0),
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    primary key (generation_id, path)
);

-- Deferred: a purge deletes the document together with its processing and generations.
alter table document add foreign key (published_generation) references generation(id)
    deferrable initially deferred;

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

-- Configured instances are space-owned data; executable templates stay in the runtime.
-- No cascade: space purge must explicitly resolve instance retention/removal first.
create table agent_instance (
    agent_instance_id uuid primary key,
    space_id uuid not null references space (id),
    template_id uuid not null,
    source_runtime_id text not null,
    source_agent_id text not null,
    display_name varchar(255) not null,
    description varchar(500),
    enabled boolean not null default true,
    created_by text,
    updated_by text,
    tuning jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
-- Names are trimmed on write; the index arbitrates concurrent creates.
create unique index uq_agent_instance_space_name on agent_instance (space_id, lower(display_name));

-- Display choices belong to the verified subject, independently of membership.
-- user_identity is a best-effort UUID directory, not an authoritative account table.
create table users_preferences (
    user_id text primary key,
    ui_theme_id text check (ui_theme_id ~ '^[a-z][a-z0-9-]{0,31}$'),
    theme_mode text not null default 'system' check (theme_mode in ('light', 'dark', 'system')),
    language text check (language in ('en', 'fr')),
    sidebar_collapsed boolean not null default false,
    team_sort_mode text not null default 'recent' check (team_sort_mode in ('recent', 'alpha')),
    agent_sort text not null default 'name' check (agent_sort in ('name', 'created_at:desc', 'updated_at:desc')),
    updated_at timestamptz not null default now()
);

-- Observations of logical pods, not deployment replicas or execution readiness.
create table runtime_catalog (
    runtime_id text primary key check (runtime_id <> '' and runtime_id = btrim(runtime_id)),
    reachable boolean not null,
    checked_at timestamptz not null default clock_timestamp(),
    observed_at timestamptz
);

create table runtime_capability (
    runtime_id text not null references runtime_catalog (runtime_id),
    capability_id text not null check (capability_id <> '' and capability_id = btrim(capability_id)),
    version text not null check (version <> '' and version = btrim(version)),
    descriptor jsonb not null check (jsonb_typeof(descriptor) = 'object'),
    advertised boolean not null,
    primary key (runtime_id, capability_id)
);

-- A single runtime key binds both the template and its capability offering.
create table runtime_template_capability (
    runtime_id text not null,
    source_agent_id text not null check (source_agent_id <> '' and source_agent_id = btrim(source_agent_id)),
    capability_id text not null,
    default_selected boolean not null,
    primary key (runtime_id, source_agent_id, capability_id),
    foreign key (runtime_id, capability_id)
        references runtime_capability (runtime_id, capability_id)
);

-- Platform sources are independent of pods. Configuration contains secret references only.
create table model_source (
    source_id text collate "C" primary key check (source_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
    configuration jsonb not null check (
        jsonb_typeof(configuration) = 'object'
        and configuration->>'source_id' = source_id
        and (configuration->>'revision')::bigint > 0
    ),
    refresh_token uuid,
    state text not null default 'not_observed'
        check (state in ('not_observed', 'ok', 'unavailable', 'invalid', 'incomplete')),
    error_code text,
    checked_at timestamptz,
    last_success_at timestamptz,
    snapshot_revision bigint not null default 0 check (snapshot_revision >= 0),
    snapshot_source_revision bigint
);

create table model_offer (
    source_id text collate "C" not null references model_source (source_id),
    upstream_model_id text collate "C" not null
        check (octet_length(upstream_model_id) between 1 and 256
               and upstream_model_id = btrim(upstream_model_id)),
    metadata jsonb not null check (jsonb_typeof(metadata) = 'object'),
    first_seen_at timestamptz not null,
    last_seen_at timestamptz not null,
    advertised boolean not null,
    withdrawn_at timestamptz,
    primary key (source_id, upstream_model_id),
    check (advertised = (withdrawn_at is null))
);

-- Organization decisions are separate from platform observations and OpenFGA authority.
create table organization_model_policy (
    organization_id uuid primary key references space (id) on delete cascade,
    revision bigint not null check (revision > 0),
    default_source_id text collate "C",
    default_upstream_model_id text collate "C",
    fallback_source_id text collate "C",
    fallback_upstream_model_id text collate "C",
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text not null,
    updated_at timestamptz not null default now(),
    check ((default_source_id is null) = (default_upstream_model_id is null)),
    check ((fallback_source_id is null) = (fallback_upstream_model_id is null))
);

create table organization_model_permission (
    organization_id uuid not null references organization_model_policy (organization_id) on delete cascade,
    source_id text collate "C" not null,
    upstream_model_id text collate "C" not null,
    reasoning_enabled boolean not null default false,
    primary key (organization_id, source_id, upstream_model_id),
    foreign key (source_id, upstream_model_id) references model_offer (source_id, upstream_model_id)
);

-- Defer membership checks until the atomic replacement is complete. A revocation must
-- explicitly clear or replace its selected default/fallback in that same transaction.
alter table organization_model_policy
    add foreign key (organization_id, default_source_id, default_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred,
    add foreign key (organization_id, fallback_source_id, fallback_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred;

create function require_model_policy_organization() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.organization_id and kind = 'organization') then
        raise exception 'model policy requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;

create trigger model_policy_organization before insert or update of organization_id
    on organization_model_policy for each row execute function require_model_policy_organization();

-- Product index only. Runtime owns messages/checkpoints. Immutable identifiers
-- deliberately have no cascading FK: retirement/purge must not erase provenance.
create table session_metadata (
    session_id uuid primary key,
    user_id text not null,
    space_id uuid not null,
    agent_instance_id uuid not null,
    template_id uuid not null,
    runtime_id text not null,
    agent_display_name varchar(255) not null,
    title varchar(500),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deletion_id uuid references deletion (id)
);
create index session_metadata_owner_activity
    on session_metadata (space_id, user_id, updated_at desc, session_id);

-- A row enables one pod offer for every space of the organization; no row denies it.
create table organization_capability (
    organization_id uuid not null references space (id) on delete cascade,
    runtime_id text not null,
    capability_id text not null,
    enabled_by text not null,
    enabled_at timestamptz not null default now(),
    primary key (organization_id, runtime_id, capability_id),
    foreign key (runtime_id, capability_id)
        references runtime_capability (runtime_id, capability_id)
);

-- Space kind is immutable, so checking the referenced space on write is sufficient.
create function require_organization_space() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.organization_id and kind = 'organization') then
        raise exception '% requires an organization', TG_TABLE_NAME using errcode = '23514';
    end if;
    return new;
end $$;

create trigger organization_capability_organization before insert or update of organization_id
    on organization_capability for each row execute function require_organization_space();
