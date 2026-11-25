-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- CP owns diagnostic policy, capture inventory and revocable owner consent.
-- Runtime owns the opaque evidence objects and erases them via leased inventory work.
create table conversation_trace_settings (
    organization_id uuid primary key references space(id) on delete cascade,
    enabled boolean not null default false,
    sampling_percent integer not null default 100 check (sampling_percent between 0 and 100),
    retention_days integer not null default 30 check (retention_days between 1 and 3650),
    storage_cap_bytes bigint not null default 20000000000 check (storage_cap_bytes between 1 and 10000000000000)
);
create table conversation_trace (
    id uuid primary key,
    session_id uuid not null references session_metadata(session_id) on delete cascade,
    organization_id uuid not null references space(id) on delete cascade,
    runtime_id text not null,
    exchange_id varchar(255) not null,
    history_rank integer not null check (history_rank >= 0),
    started_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz not null,
    retired boolean not null default false,
    unique(session_id,exchange_id)
);
create index conversation_trace_catalog on conversation_trace(organization_id,started_at desc,id) where not retired;
create index conversation_trace_expiry on conversation_trace(runtime_id,expires_at);
create table conversation_trace_segment (
    id uuid primary key,
    capture_id uuid not null references conversation_trace(id) on delete cascade,
    started_at timestamptz not null default clock_timestamp(),
    facts jsonb not null default '{}',
    complete boolean not null default false
);
create index conversation_trace_segment_capture on conversation_trace_segment(capture_id,started_at,id);
-- A small indexed projection links malformed tool fragments back to their first
-- observed model call without expanding every saved JSON call on each read.
create table conversation_trace_model_origin (
    segment_id uuid not null references conversation_trace_segment(id) on delete cascade,
    call_order integer not null check(call_order>=0),
    fingerprint varchar(64) not null check(fingerprint ~ '^[0-9a-f]{64}$'),
    call_id varchar(255) not null,
    observed_through_rank integer not null check(observed_through_rank>=0),
    primary key(segment_id,call_order,fingerprint)
);
create index conversation_trace_model_origin_fingerprint on conversation_trace_model_origin(fingerprint,segment_id,call_order);
create table conversation_trace_consent (
    session_id uuid primary key references session_metadata(session_id) on delete cascade,
    version uuid not null,
    cutoff jsonb,
    title text,
    incidents jsonb not null default '[]',
    updated_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz not null default clock_timestamp()+interval '30 days'
);
create index conversation_trace_consent_expiry on conversation_trace_consent(expires_at) where cutoff is not null;
-- Kept after catalogue deletion until the owning runtime confirms physical erasure.
-- Quota includes uncertain and pending PUTs until that confirmation.
create table conversation_trace_object (
    ref varchar(32) primary key check (ref ~ '^[0-9a-f]{32}$'),
    capture_id uuid not null,
    segment_id uuid not null,
    publication_id uuid not null,
    organization_id uuid not null,
    runtime_id text not null,
    session_id uuid not null,
    reserved_bytes bigint not null check (reserved_bytes between 0 and 16777216),
    stored_bytes bigint check (stored_bytes between 0 and reserved_bytes),
    reserved_at timestamptz not null default clock_timestamp(),
    cleanup_after timestamptz,
    lease uuid,
    leased_until timestamptz
);
create index conversation_trace_object_session on conversation_trace_object(session_id);
create index conversation_trace_object_capture on conversation_trace_object(capture_id);
create index conversation_trace_object_quota on conversation_trace_object(organization_id);
create index conversation_trace_object_cleanup on conversation_trace_object(runtime_id,cleanup_after,leased_until);
create function retire_trace_objects() returns trigger language plpgsql as $$
begin
    update conversation_trace_object set cleanup_after = coalesce(cleanup_after,clock_timestamp()+interval '1 minute')
      where capture_id=old.id;
    return old;
end $$;
create trigger conversation_trace_erasure before delete on conversation_trace
    for each row execute function retire_trace_objects();
create function retire_session_traces() returns trigger language plpgsql as $$
begin
    update conversation_trace set retired=true where session_id=new.session_id;
    update conversation_trace_object set cleanup_after=coalesce(cleanup_after,clock_timestamp()+interval '1 minute')
      where session_id=new.session_id;
    delete from conversation_trace_consent where session_id=new.session_id;
    return new;
end $$;
create trigger session_trace_retirement after update of deletion_id on session_metadata
    for each row when (new.deletion_id is not null and old.deletion_id is null)
    execute function retire_session_traces();
comment on trigger session_trace_retirement on session_metadata is
    'effect: session retirement immediately revokes diagnostics and schedules physical evidence erasure';
comment on trigger conversation_trace_erasure on conversation_trace is
    'effect: deleting capture metadata preserves durable evidence cleanup inventory';
