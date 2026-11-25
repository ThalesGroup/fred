-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Deployment sources and organization-owned connections publish through the same
-- inventory. The owning row contains the encrypted credential, never configuration
-- JSON or a public projection. Retained source/offer keys preserve corpus provenance
-- after deletion; deleting an organization also removes its credential.
alter table model_source add column managed boolean not null default false;
create table organization_model_catalog (
    source_id text collate "C" primary key references model_source(source_id),
    organization_id uuid not null references space(id) on delete cascade,
    name text not null check (length(btrim(name)) between 1 and 128),
    encrypted_token bytea,
    deleted_at timestamptz,
    check ((deleted_at is null) = (encrypted_token is not null))
);
create index organization_model_catalog_owner on organization_model_catalog(organization_id);
create trigger model_catalog_organization before insert or update of organization_id
    on organization_model_catalog for each row execute function require_model_policy_organization();
comment on trigger model_catalog_organization on organization_model_catalog is
    'assertion: consistency - a catalogue belongs to an organization';
create function require_owned_model_source() returns trigger language plpgsql as $$
begin
    if exists(select 1 from model_source where source_id=new.source_id and managed)
       and not exists(select 1 from organization_model_catalog where source_id=new.source_id
           and organization_id=new.organization_id and deleted_at is null) then
        raise exception 'model catalogue belongs to another organization' using errcode='23514';
    end if;
    return new;
end $$;
create trigger model_source_owner before insert or update on organization_model_source
    for each row execute function require_owned_model_source();
comment on trigger model_source_owner on organization_model_source is
    'assertion: consistency - only the owning organization can assign its managed catalogue';

-- Complements belong to an organization, including for a shared deployment source.
-- One owner's corrections must never change another organization's model facts.
create table organization_model_metadata (
    organization_id uuid not null references space(id) on delete cascade,
    source_id text collate "C" not null,
    upstream_model_id text collate "C" not null,
    complements jsonb not null default '{}'::jsonb check(jsonb_typeof(complements)='object'),
    revision bigint not null default 0 check(revision>=0),
    primary key(organization_id,source_id,upstream_model_id),
    foreign key(source_id,upstream_model_id) references model_offer(source_id,upstream_model_id),
    foreign key(organization_id,source_id) references organization_model_source(organization_id,source_id) on delete cascade
);

create function effective_model_metadata(org uuid,source text,model text) returns jsonb
    language sql stable security definer set search_path=control_plane,pg_temp as $$
    select o.metadata || coalesce(c.complements,'{}'::jsonb)
        || jsonb_build_object('provenance',coalesce(o.metadata->'provenance','{}'::jsonb)||coalesce(c.provenance,'{}'::jsonb))
    from model_offer o left join lateral (
        select jsonb_object_agg(x.key,x.value) as complements,
            jsonb_object_agg(x.key,'manual'::text) as provenance
        from organization_model_metadata m cross join lateral jsonb_each(m.complements) x
        where m.organization_id=org and m.source_id=source and m.upstream_model_id=model
            and (x.key='display_name' or o.metadata->'provenance'->>x.key is distinct from 'provider')
            and not coalesce((x.key='embedding' and o.metadata->'chat'='true'::jsonb and o.metadata->'provenance'->>'chat'='provider'),false)
            and not coalesce((x.key='chat' and o.metadata->'embedding'='true'::jsonb and o.metadata->'provenance'->>'embedding'='provider'),false)
            and not coalesce((x.key like 'reasoning\_%' escape '\' and o.metadata->'reasoning'='false'::jsonb and o.metadata->'provenance'->>'reasoning'='provider'),false)
    ) c on true where o.source_id=source and o.upstream_model_id=model
$$;
revoke execute on function effective_model_metadata(uuid,text,text) from public;
grant execute on function effective_model_metadata(uuid,text,text) to fred_kf_reader;

-- Organization-owned access positions, separate from a team's own restrictions.
-- No row means inheritance. A null team_id addresses all personal spaces, never
-- an individual user. Enabled never grants a model outside organization permission.
create table organization_model_scope (
    organization_id uuid not null,
    source_id text collate "C" not null,
    upstream_model_id text collate "C" not null,
    team_id uuid,
    enabled boolean not null,
    updated_by text not null,
    updated_at timestamptz not null default clock_timestamp(),
    unique nulls not distinct (organization_id, source_id, upstream_model_id, team_id),
    foreign key (organization_id, source_id)
        references organization_model_source (organization_id, source_id) on delete cascade,
    foreign key (source_id, upstream_model_id)
        references model_offer (source_id, upstream_model_id),
    foreign key (team_id, organization_id)
        references space (id, organization_id) on delete cascade
);
create index organization_model_scope_restrictions
    on organization_model_scope (organization_id, team_id, source_id, upstream_model_id)
    where not enabled;

create function require_model_scope_team() returns trigger language plpgsql as $$
begin
    if new.team_id is not null and not exists (
        select 1 from space where id = new.team_id and organization_id = new.organization_id
            and kind = 'team' and deletion_id is null
    ) then
        raise exception 'model scope requires an active team in its organization' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger organization_model_scope_team before insert or update on organization_model_scope
    for each row execute function require_model_scope_team();
comment on trigger organization_model_scope_team on organization_model_scope is
    'assertion: consistency - organization model access targets an active local team or the personal class';

-- Temporal delivers each reconstruction into a separate physical namespace.
-- A manual resume gets a new execution identity and keeps its corpus and cursor.
create table organization_vector_reindex (
    id uuid primary key,
    organization_id uuid not null references space(id) on delete cascade,
    requested_by text not null,
    status text not null check(status in ('pending','running','failed','succeeded')),
    admission jsonb not null,
    cursor uuid,
    completed bigint not null default 0 check(completed>=0),
    total bigint not null check(total>=0),
    lease uuid,
    lease_until timestamptz,
    document_id uuid,
    chunk_cursor bigint not null default 0 check(chunk_cursor>=0),
    deadline_at timestamptz not null default clock_timestamp()+interval '1 day',
    error_code text,
    created_at timestamptz not null default clock_timestamp(),
    completed_at timestamptz,
    execution_id uuid not null default gen_random_uuid(),
    dispatch_after timestamptz not null default clock_timestamp(),
    unique(organization_id,id)
);
create index vector_reindex_due on organization_vector_reindex(dispatch_after,id)
    where status in ('pending','running');
create unique index vector_reindex_active on organization_vector_reindex(organization_id)
    where status in ('pending','running');
create index vector_reindex_latest on organization_vector_reindex(organization_id,created_at desc,id desc);
-- Storage retirement outlives an organization; no FK may discard this intent
-- before a remote store has actually been removed.
create table vector_corpus_retirement (
    organization_id uuid not null,
    corpus_generation uuid,
    due_at timestamptz not null default clock_timestamp(),
    replaced_by uuid,
    cleaned_at timestamptz,
    unique nulls not distinct(organization_id,corpus_generation)
);
create index vector_corpus_retirement_due on vector_corpus_retirement(due_at);
create unique index vector_corpus_replacement on vector_corpus_retirement(replaced_by)
    where replaced_by is not null;

-- Keep the active corpus and both dedicated model choices in the atomic policy.
alter table organization_model_policy
    add column corpus_generation uuid,
    add foreign key(organization_id,corpus_generation) references organization_vector_reindex(organization_id,id) deferrable initially deferred,
    add column creation_assistant_source_id text collate "C",
    add column creation_assistant_upstream_model_id text collate "C",
    add check ((creation_assistant_source_id is null) = (creation_assistant_upstream_model_id is null)),
    add foreign key (organization_id, creation_assistant_source_id, creation_assistant_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred,
    add column transcription_source_id text collate "C",
    add column transcription_upstream_model_id text collate "C",
    add check ((transcription_source_id is null) = (transcription_upstream_model_id is null)),
    add foreign key (organization_id, transcription_source_id, transcription_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred;

-- The unpublished target also needs physical cleanup if the organization is purged.
create function retire_organization_corpus() returns trigger language plpgsql as $$
begin
    insert into vector_corpus_retirement(organization_id,corpus_generation)
        values(old.organization_id,old.corpus_generation) on conflict do nothing;
    insert into vector_corpus_retirement(organization_id,corpus_generation)
        select organization_id,id from organization_vector_reindex
        where organization_id=old.organization_id and status<>'succeeded' on conflict do nothing;
    return old;
end $$;
create trigger retire_organization_corpus before delete on organization_model_policy
    for each row execute function retire_organization_corpus();
comment on trigger retire_organization_corpus on organization_model_policy is
    'effect: retain physical corpus retirement after organization deletion';

-- Policy always points at the active generation, including during reconstruction.
-- The worker's final receipt and the policy swap are committed together.
create or replace function keep_locked_embedding() returns trigger language plpgsql as $$
begin
    if tg_op='DELETE' then
        if old.embedding_locked_at is not null and exists(select 1 from space where id=old.organization_id) then
            raise exception 'the indexed corpus keeps its embedding model' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
        return old;
    end if;
    if new.corpus_generation is distinct from old.corpus_generation then
        if new.embedding_locked_at is distinct from old.embedding_locked_at or not exists(
            select 1 from organization_vector_reindex r
            where r.organization_id=new.organization_id and r.id=new.corpus_generation and r.status='succeeded'
              and r.admission->'selection'->'key'->>'source_id'=new.embedding_source_id
              and r.admission->'selection'->'key'->>'upstream_model_id'=new.embedding_upstream_model_id
        ) then
            raise exception 'activating a corpus requires a successful reconstruction' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
        end if;
    elsif old.embedding_locked_at is not null
        and (new.embedding_source_id,new.embedding_upstream_model_id,new.embedding_locked_at)
            is distinct from (old.embedding_source_id,old.embedding_upstream_model_id,old.embedding_locked_at) then
        raise exception 'the indexed corpus keeps its embedding model; changing it requires reindexing' using errcode='23514',constraint=TG_NAME,table=TG_TABLE_NAME;
    end if;
    return new;
end $$;

comment on trigger organization_embedding_locked on organization_model_policy is
    'assertion: consistency - an indexed corpus changes models only after successful reconstruction';

-- A selection can try an unclassified offer. Known uses and explicit refusals
-- still govern eligibility. Keep policy, admission and document readers aligned.
create function model_use_options(metadata jsonb) returns jsonb
    language sql immutable strict as $$
    with reported as (
        select metadata->'chat' as chat,
               metadata->'embedding' as embedding,
               metadata->'vision' as vision,
               coalesce(nullif(metadata->'audio_transcription', 'null'::jsonb),
                        metadata->'provider_capabilities'->'audio_transcription') as transcription
    ), classified as (
        select *, not coalesce('true'::jsonb in (chat, embedding, vision, transcription), false)
            and not exists (
                select 1 from unnest(array['completion_fim', 'classification', 'ocr',
                    'audio_transcription_realtime', 'audio_generation', 'speech_generation']) as capability(name)
                where metadata->'provider_capabilities'->capability.name = 'true'::jsonb
            ) as unverified
        from reported
    ), options as (
        select unverified, vision,
               coalesce(chat='true'::jsonb, false) or
                   (unverified and chat is distinct from 'false'::jsonb) as can_chat,
               coalesce(embedding='true'::jsonb, false) or
                   (unverified and embedding is distinct from 'false'::jsonb) as can_embed,
               coalesce(transcription='true'::jsonb, false) or
                   (unverified and transcription is distinct from 'false'::jsonb) as can_transcribe
        from classified
    )
    select jsonb_build_object('unverified', unverified, 'chat', can_chat, 'embedding', can_embed,
        'vision', can_chat and vision is distinct from 'false'::jsonb, 'transcription', can_transcribe)
    from options
$$;
revoke execute on function model_use_options(jsonb) from public;
grant execute on function model_use_options(jsonb) to fred_kf_reader;

-- Only encrypted credentials cross the private reader boundary.
create or replace view cp_read.organization_model as
select s.id as space_id, p.organization_id, u.use, u.source_id, u.upstream_model_id,
       m.configuration->'inference' as connection,
       (m.configuration->>'revision')::bigint as source_revision,
       m.snapshot_revision, p.revision as policy_revision,
       coalesce((m.configuration->>'enabled')::boolean, false)
           and m.snapshot_source_revision is not distinct from (m.configuration->>'revision')::bigint
           and coalesce(o.advertised, false)
           and coalesce(model_use_options(effective_model_metadata(p.organization_id,o.source_id,o.upstream_model_id)) -> u.use = 'true'::jsonb, false)
           and (u.use<>'embedding' or not exists(select 1 from organization_vector_reindex r where r.id=p.corpus_generation and r.status<>'succeeded')) as available,
       encode(c.encrypted_token,'base64') as encrypted_credential, p.corpus_generation
from space s
join organization_model_policy p on p.organization_id = s.organization_id
cross join lateral (values
    ('embedding', p.embedding_source_id, p.embedding_upstream_model_id, p.embedding_locked_at is not null),
    ('chat', p.default_source_id, p.default_upstream_model_id, true)
) as u(use, source_id, upstream_model_id, applies)
join model_source m on m.source_id = u.source_id
left join organization_model_catalog c on c.source_id=m.source_id and c.organization_id=p.organization_id and c.deleted_at is null
left join model_offer o on o.source_id = u.source_id and o.upstream_model_id = u.upstream_model_id
where u.applies;
-- space_id/use select the row; use also names the aptitude in the offer metadata.
grant select on cp_read.organization_model to fred_kf_reader;
