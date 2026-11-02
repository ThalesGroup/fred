-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Weaver initial schema. Fresh databases only; no incremental upgrade path.
-- SQLx executes this file atomically and records its fingerprint for startup checks.

create type space_kind as enum ('organization', 'team', 'project', 'personal');

-- Operational receipts outlive their target.
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
-- organization lock. Placement and initial grants commit atomically.
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
    ),
    constraint space_placement_shape check (
        (kind = 'organization' and organization_id = id and parent_id is null)
        or (kind = 'personal' and organization_id <> id and parent_id is null)
        or (kind = 'team' and organization_id <> id and parent_id = organization_id and parent_id is not null)
        or (kind = 'project' and organization_id <> id and parent_id is not null and parent_id <> id)
    ),
    constraint space_id_organization_key unique (id, organization_id),
    constraint space_parent_organization_fkey foreign key (parent_id, organization_id)
        references space (id, organization_id)
);
comment on column space.personal_owner is 'Owner identity of a personal space; null for other space kinds';
create unique index space_organization_name on space (name) where kind = 'organization';
create index space_deletion_manifest on space (deletion_id, kind, id) where deletion_id is not null;
create index space_organization on space (organization_id);
create index space_parent on space (parent_id);
-- Retired siblings keep their names until purge.
create unique index space_sibling_name on space (parent_id, name) where kind in ('team', 'project');
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

-- A conversation attachment has a session and no folder; only its owner reaches it,
-- through the conversation routes. Drive reads and counters exclude it, quota does not.
create table document (
    id          uuid primary key,
    space_id    uuid not null references space (id),
    folder_id   uuid,             -- null means the space root, or an attachment
    session_id  uuid,             -- the owning conversation; foreign key below
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
    purge_after timestamptz,      -- purge queue order; each claim pushes it back
    deletion_id uuid references deletion (id),
    foreign key (folder_id, space_id) references folder (id, space_id),
    constraint document_size_valid check (size >= 0 and size <= 104857600),
    constraint document_digest_valid check (sha256 ~ '^[0-9a-f]{64}$'),
    constraint document_retrieval_command check (
        num_nulls(retrieval_id, retrieval_actor, retrieval_target, retrieval_phase, retrieval_confirmed) in (0, 5)
    ),
    check (purged_at is null or deletion_id is not null),
    check ((purge_after is null) = (deletion_id is null)),
    check (session_id is null or folder_id is null)
);
create index document_quota_owner on document (quota_owner) include (size);
create index document_deletion_manifest on document (deletion_id) where deletion_id is not null;
create index document_purge on document (purge_after, id) where deletion_id is not null and purged_at is null;
create index document_session on document (session_id) where session_id is not null;
create unique index document_space_id_folder_id_name_key on document (space_id, folder_id, session_id, name)
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
    if (new.space_id, new.folder_id, new.session_id) is distinct from (old.space_id, old.folder_id, old.session_id) then
        raise exception 'document placement is immutable';
    end if;
    return new;
end $$;

create trigger space_immutable before update on space for each row execute function forbid_space_move();
create trigger folder_immutable before update on folder for each row execute function forbid_folder_move();
create trigger document_immutable before update on document for each row execute function forbid_document_move();

-- Durable root-bootstrap marker, committed atomically with the first administrator.
create table platform_bootstrap (
    singleton    boolean primary key default true check (singleton),
    completed_by text not null,
    completed_at timestamptz not null default now(),
    granted_at   timestamptz not null default now()
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
-- A stored upload's id is its document's id. Its destination is a folder or a conversation.
create table document_upload (
    id uuid primary key,
    request_key uuid not null,
    actor text not null,
    organization_id uuid not null,
    space_id uuid not null,
    folder_id uuid,
    session_id uuid,
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
    check((status = 'pending') = (completed_at is null)),
    check((folder_id is null) = (session_id is not null))
);
create unique index document_upload_active_name on document_upload(space_id, folder_id, session_id, name)
    nulls not distinct where status = 'pending';
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
    check((status in ('succeeded','failed')) = (completed_at is not null)),
    constraint document_processing_id_document_key unique (id, document_id)
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
    processing_id uuid not null,
    document_id uuid not null,
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
    -- Cleanup queue order: the lease end plus 60 s, pushed back by each claim.
    cleanup_after timestamptz not null,
    cleaned_at timestamptz,
    constraint generation_processing_document_fkey foreign key (processing_id, document_id)
        references document_processing (id, document_id) on delete cascade,
    constraint generation_id_document_key unique (id, document_id)
);
create index generation_processing on generation(processing_id,created_at,id);
create index generation_cleanup on generation(cleanup_after,id) where cleaned_at is null;

-- Committed outputs; preview checks the size, KF and publication check the digest.
create table artifact (
    generation_id uuid not null references generation(id) on delete cascade,
    path text not null,
    size bigint not null check(size>=0),
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    primary key (generation_id, path)
);

-- Deferred: a purge deletes the document together with its processing and generations.
alter table document add constraint document_published_generation_fkey
    foreign key (published_generation, id) references generation(id, document_id)
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
    created_by text not null,
    updated_by text not null,
    tuning jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    configuration_revision bigint not null default 1 check (configuration_revision > 0),
    logical_name text collate "C" not null check (logical_name ~ '^[a-z0-9_-]{1,64}$'),
    constraint agent_instance_space_logical_name_key unique (space_id, logical_name)
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
    snapshot_source_revision bigint,
    constraint model_source_required_configuration_fields check (
        configuration->>'source_id' is not null and configuration->>'revision' is not null
    )
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

-- Organization decisions are separate from platform observations and platform authority.
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
    deletion_id uuid references deletion (id),
    agent_configuration_revision bigint not null check (agent_configuration_revision > 0),
    -- Provenance survives independent agent/space purge; no foreign key.
    agent_space_id uuid
);
create index session_metadata_owner_activity
    on session_metadata (space_id, user_id, updated_at desc, session_id);

-- An attachment lives in its conversation's space.
alter table session_metadata add unique (session_id, space_id);
alter table document add foreign key (session_id, space_id)
    references session_metadata (session_id, space_id);

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

-- Direct business roles. All mutations share the platform/organization advisory locks.
create table platform_role_grant (
 subject text not null,
 role text not null check (role in ('platform_admin','platform_observer','feature_manager','prompt_editor')),
 primary key(subject, role)
);
create table space_role_grant (
 space_id uuid not null references space(id) on delete cascade,
 subject text not null,
 role text not null check (role in ('member','editor','owner','analyst','organization_admin')),
 primary key(space_id, subject, role)
);
create index space_role_subject on space_role_grant(subject, space_id);
create table agent_template_policy (
 organization_id uuid not null references space(id) on delete cascade,
 template_id uuid not null,
 primary key(organization_id, template_id)
);

-- Referenced kinds and placement are immutable; only creation needs this check.
create function require_space_hierarchy() returns trigger language plpgsql as $$
begin
    if new.kind <> 'organization' and not exists (
        select 1 from space where id = new.organization_id and kind = 'organization'
    ) then
        raise exception 'space requires an organization root' using errcode = '23514';
    end if;
    if new.kind = 'project' and not exists (
        select 1 from space where id = new.parent_id and kind = 'team'
    ) then
        raise exception 'project requires a team parent' using errcode = '23514';
    end if;
    return new;
end $$;

create trigger space_hierarchy after insert on space
    for each row execute function require_space_hierarchy();

create function require_space_role_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
    target_owner text;
begin
    select kind, personal_owner into target_kind, target_owner from space where id = new.space_id;
    if target_kind = 'personal' and target_owner <> new.subject then
        raise exception 'personal space roles require its owner' using errcode = '23514';
    end if;
    if new.role = 'organization_admin' and target_kind <> 'organization' then
        raise exception 'organization admin requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;

create trigger space_role_scope before insert or update of space_id, subject, role
    on space_role_grant for each row execute function require_space_role_scope();


create trigger agent_template_policy_organization before insert or update of organization_id
    on agent_template_policy for each row execute function require_organization_space();

-- Storage only: the Control Plane still uses configured limits and live sums.
-- Populate these accounts only together with transactional counter maintenance.
create table storage_budget (
    space_id uuid not null references space(id) on delete cascade,
    scope text not null check (scope in ('local', 'organization_total')),
    limit_bytes bigint not null check (limit_bytes > 0),
    used_bytes bigint not null check (used_bytes >= 0),
    reserved_bytes bigint not null check (reserved_bytes >= 0),
    primary key (space_id, scope)
);
-- A limit can fall below existing usage; admission must then refuse new bytes.
-- No zero defaults: initialization must account for existing originals/uploads.
comment on table storage_budget is
    'Original-file usage and pending uploads only; excludes derived outputs and retired documents. Local and organization_total accounts overlap and must not be summed together.';

create function require_storage_budget_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
begin
    if TG_OP = 'UPDATE' then
        if (new.space_id, new.scope) is distinct from (old.space_id, old.scope) then
            raise exception 'storage budget identity is immutable' using errcode = '23514';
        end if;
        return new;
    end if;
    select kind into target_kind from space where id = new.space_id;
    if target_kind = 'project' then
        raise exception 'projects share their team storage budget' using errcode = '23514';
    end if;
    if new.scope = 'organization_total' and target_kind <> 'organization' then
        raise exception 'total storage budget requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger storage_budget_scope before insert or update on storage_budget
    for each row execute function require_storage_budget_scope();

-- Categories belong to the prompt's space, never to a global taxonomy.
create table prompt_category (
    id uuid primary key,
    space_id uuid not null references space (id) on delete cascade,
    name varchar(120) not null check (btrim(name) <> ''),
    constraint prompt_category_space_name_key unique (space_id, name),
    constraint prompt_category_space_id_key unique (space_id, id)
);


-- One canonical ASCII name per type and space. The prompt command is '/' || logical_name.
-- Reject noncanonical input instead of silently renaming resources or promotions.
create table prompt (
    prompt_id uuid primary key,
    space_id uuid not null references space (id) on delete cascade,
    logical_name text collate "C" not null
        check (logical_name ~ '^[a-z0-9_-]{1,64}$')
        check (logical_name <> 'skill'), -- Existing reserved slash command, not a skill schema.
    display_name varchar(255) not null check (btrim(display_name) <> ''),
    description text,
    text text not null,
    created_at timestamptz not null default now(),
    created_by text not null check (btrim(created_by) <> ''),
    updated_at timestamptz not null default now(),
    updated_by text not null check (btrim(updated_by) <> ''),
    constraint prompt_space_logical_name_key unique (space_id, logical_name),
    category_id uuid,
    tags text[] not null default '{}' check (cardinality(tags) <= 20 and array_position(tags, null) is null),
    published boolean not null default false,
    constraint prompt_nonblank_text check (text ~ '[^[:space:]]'),
    constraint prompt_category_same_space_fkey foreign key (space_id, category_id)
        references prompt_category (space_id, id)
);

-- NO ACTION protects used categories while allowing the owning space's atomic purge.
create index prompt_space_category_idx on prompt (space_id, category_id);

create function protect_prompt_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if (new.prompt_id, new.space_id, new.logical_name, new.created_at, new.created_by)
            is distinct from
            (old.prompt_id, old.space_id, old.logical_name, old.created_at, old.created_by) then
            raise exception 'prompt identity and creation metadata are immutable' using errcode = '23514';
        end if;
        if (new.display_name, new.description, new.text, new.category_id, new.tags)
            is distinct from (old.display_name, old.description, old.text, old.category_id, old.tags) then
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;
create trigger prompt_definition before insert or update on prompt
    for each row execute function protect_prompt_definition();

-- Like users_preferences, the verified subject is text. user_identity is a
-- best-effort directory cache, not the account authority and cannot own this FK.
-- Account erasure must purge this table alongside users_preferences. Access
-- revocation retains the preference; authorized reads never expose it without access.
create table prompt_favorite (
    user_id text not null check (btrim(user_id) <> ''),
    prompt_id uuid not null references prompt(prompt_id) on delete cascade,
    primary key (user_id, prompt_id)
);
create index prompt_favorite_prompt_idx on prompt_favorite(prompt_id);

create function require_prompt_publication_team() returns trigger language plpgsql as $$
begin
    if new.published and not exists (
        select 1 from space where id = new.space_id and kind = 'team'
    ) then
        raise exception 'only team prompts can be published' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger prompt_publication_team before insert or update of published, space_id on prompt
    for each row execute function require_prompt_publication_team();

-- The organization is derived from placement. Walk each team's published UUIDs
-- without reading private definitions; UUID is an immutable keyset cursor.
create index prompt_published_space_id on prompt (space_id, prompt_id) where published;

-- Authenticated writers supply author identities. Logical identity is immutable.
create function protect_agent_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.created_by is null or btrim(new.created_by) = '' then
            raise exception 'agent creation requires an author' using errcode = '23514';
        end if;
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if new.logical_name is distinct from old.logical_name then
            raise exception 'agent logical name is immutable' using errcode = '23514';
        end if;
        if (new.agent_instance_id, new.space_id, new.template_id, new.source_runtime_id,
                new.source_agent_id, new.created_at, new.created_by)
            is distinct from
            (old.agent_instance_id, old.space_id, old.template_id, old.source_runtime_id,
                old.source_agent_id, old.created_at, old.created_by) then
            raise exception 'agent identity, placement and creation metadata are immutable'
                using errcode = '23514';
        end if;
        if (new.display_name, new.description, new.enabled, new.tuning)
            is distinct from (old.display_name, old.description, old.enabled, old.tuning) then
            if new.updated_by is null or btrim(new.updated_by) = '' then
                raise exception 'agent edit requires an author' using errcode = '23514';
            end if;
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;
create trigger agent_definition before insert or update on agent_instance
    for each row execute function protect_agent_definition();

create function protect_session_association() returns trigger language plpgsql as $$
declare
    deployment uuid;
    agent_organization uuid;
    chat_organization uuid;
    agent_template uuid;
    agent_runtime text;
begin
    if tg_op = 'INSERT' then
        -- Hold the association's sources through commit, including against concurrent purge.
        select a.space_id, sa.organization_id, sc.organization_id, a.template_id, a.source_runtime_id
            into deployment, agent_organization, chat_organization, agent_template, agent_runtime
            from agent_instance a
            join space sa on sa.id = a.space_id
            join space sc on sc.id = new.space_id
            where a.agent_instance_id = new.agent_instance_id
            for key share of a, sa, sc;
        if not found then
            raise exception 'conversation requires an existing agent and conversation space'
                using errcode = '23503';
        end if;
        if (new.agent_space_id is not null and new.agent_space_id <> deployment)
            or agent_organization <> chat_organization
            or new.template_id <> agent_template or new.runtime_id <> agent_runtime then
            raise exception 'conversation agent association is inconsistent' using errcode = '23514';
        end if;
        new.agent_space_id := deployment;
    elsif (new.session_id, new.space_id, new.user_id, new.agent_instance_id,
            new.agent_space_id, new.template_id, new.runtime_id)
        is distinct from
          (old.session_id, old.space_id, old.user_id, old.agent_instance_id,
            old.agent_space_id, old.template_id, old.runtime_id) then
        raise exception 'conversation ownership and agent association are immutable'
            using errcode = '23514';
    end if;
    return new;
end $$;

create trigger session_association before insert or update on session_metadata
    for each row execute function protect_session_association();

-- Preparation only: document_immutable still forbids changing document placement.
-- These receipts neither move data nor schedule work; activation needs the SQL/index writer.
create table document_move (
    id uuid primary key,
    document_id uuid not null references document(id) on delete cascade,
    actor text not null check (btrim(actor) <> ''),
    source_space_id uuid not null,
    source_folder_id uuid,
    destination_space_id uuid not null,
    destination_folder_id uuid,
    generation_id uuid,
    phase text not null default 'requested'
        check (phase in ('requested', 'projecting', 'completed', 'cancelled')),
    created_at timestamptz not null default now() check (isfinite(created_at)),
    finished_at timestamptz check (isfinite(finished_at)),
    check ((phase in ('completed', 'cancelled')) = (finished_at is not null)),
    check (finished_at >= created_at),
    check ((source_space_id, source_folder_id)
        is distinct from (destination_space_id, destination_folder_id))
);
create unique index document_move_active on document_move(document_id)
    where phase in ('requested', 'projecting');
create index document_move_history on document_move(document_id, created_at desc, id);

-- Placement/generation are historical facts, not permanent FKs that block purge.
-- Only the document owns the receipt; its definitive purge removes the receipts.
create function protect_document_move() returns trigger language plpgsql as $$
declare
    source document%rowtype;
    source_organization uuid;
    destination_organization uuid;
begin
    if tg_op = 'INSERT' then
        if new.phase <> 'requested' or new.finished_at is not null then
            raise exception 'a document move starts as requested' using errcode = '23514';
        end if;
        select * into source from document where id = new.document_id for update;
        if not found then
            raise exception 'document move requires an existing document' using errcode = '23503';
        end if;
        if source.session_id is not null or source.deletion_id is not null then
            raise exception 'only live drive documents can be moved' using errcode = '23514';
        end if;
        if source.retrievable_pending or exists (
            select 1 from document_processing where document_id = source.id
                and status in ('pending', 'running')
        ) then
            raise exception 'document has unfinished processing or inclusion work' using errcode = '23514';
        end if;
        select organization_id into source_organization
            from space where id = source.space_id and deletion_id is null for share;
        if not found then
            raise exception 'source space must be live' using errcode = '23514';
        end if;
        select organization_id into destination_organization
            from space where id = new.destination_space_id and deletion_id is null for share;
        if not found then
            raise exception 'destination space must exist and be live' using errcode = '23503';
        end if;
        if source_organization <> destination_organization then
            raise exception 'document move must stay within one organization' using errcode = '23514';
        end if;
        if new.destination_folder_id is not null then
            perform 1 from folder where id = new.destination_folder_id
                and space_id = new.destination_space_id and deletion_id is null for share;
            if not found then
                raise exception 'destination folder must be live in destination space' using errcode = '23503';
            end if;
        end if;
        -- Always capture database facts, never source placement asserted by the caller.
        new.source_space_id := source.space_id;
        new.source_folder_id := source.folder_id;
        new.generation_id := source.published_generation;
    else
        if (new.id, new.document_id, new.actor, new.source_space_id, new.source_folder_id,
                new.destination_space_id, new.destination_folder_id, new.generation_id, new.created_at)
            is distinct from
            (old.id, old.document_id, old.actor, old.source_space_id, old.source_folder_id,
                old.destination_space_id, old.destination_folder_id, old.generation_id, old.created_at) then
            raise exception 'document move request is immutable' using errcode = '23514';
        end if;
        if new.phase = old.phase then
            if new.finished_at is distinct from old.finished_at then
                raise exception 'document move outcome is immutable' using errcode = '23514';
            end if;
            return new;
        end if;
        if not ((old.phase = 'requested' and new.phase in ('projecting', 'cancelled'))
            or (old.phase = 'projecting' and new.phase = 'completed')) then
            raise exception 'invalid document move transition' using errcode = '23514';
        end if;
        if new.phase in ('projecting', 'completed') then
            select * into source from document where id = new.document_id for update;
            if not found then
                raise exception 'document move requires an existing document' using errcode = '23503';
            end if;
            if (source.space_id, source.folder_id, source.published_generation)
                is distinct from
                (new.destination_space_id, new.destination_folder_id, new.generation_id)
                or source.session_id is not null or source.deletion_id is not null then
                raise exception 'document move placement or generation does not match' using errcode = '23514';
            end if;
        end if;
        if new.phase in ('completed', 'cancelled') then
            new.finished_at := clock_timestamp();
        end if;
    end if;
    return new;
end $$;
create trigger document_move_identity before insert or update on document_move
    for each row execute function protect_document_move();

-- Placement lookups and foreign-key checks must include retired documents.
create index document_space_folder on document (space_id, folder_id);

-- Purge selects each space's folders in ID order, including retired rows.
create index folder_space on folder (space_id, id);

-- Leaf detection looks up children by parent alone, regardless of deletion state.
create index folder_parent on folder (parent_id) where parent_id is not null;

-- Explicit platform assignments; discovery never grants organization access.
create table organization_model_source (
    organization_id uuid not null references space (id) on delete cascade,
    source_id text collate "C" not null references model_source (source_id),
    primary key (organization_id, source_id)
);
create trigger model_source_organization before insert or update of organization_id
    on organization_model_source for each row execute function require_model_policy_organization();

-- A row also remembers an administered policy, even after that policy is deleted.
-- completed_at additionally records completion of the one-time source assignment.
-- Neither deleting permissions/policy nor removing YAML resets this receipt.
create table organization_model_initialization (
    organization_id uuid primary key references space (id) on delete cascade,
    completed_at timestamptz
);
create trigger model_initialization_organization before insert or update of organization_id
    on organization_model_initialization for each row execute function require_model_policy_organization();

create function remember_model_policy_initialization() returns trigger language plpgsql as $$
begin
    insert into organization_model_initialization (organization_id) values (new.organization_id)
        on conflict (organization_id) do nothing;
    return new;
end $$;
create trigger remember_model_policy after insert on organization_model_policy
    for each row execute function remember_model_policy_initialization();

-- Every permission requires an explicit platform source assignment from creation.
alter table organization_model_permission
    add constraint organization_model_permission_source_assignment
    foreign key (organization_id, source_id)
    references organization_model_source (organization_id, source_id);
