-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- The organization's document models, decided with its chat models. Knowledge Flow
-- embeds the organization's corpus with one model: the first indexing claim locks it,
-- since a vector index cannot mix embedding spaces. Vision describes document images.
set local lock_timeout = '5s';

alter table organization_model_policy
    add column embedding_source_id text collate "C",
    add column embedding_upstream_model_id text collate "C",
    add column embedding_locked_at timestamptz,
    add column vision_source_id text collate "C",
    add column vision_upstream_model_id text collate "C",
    add check ((embedding_source_id is null) = (embedding_upstream_model_id is null)),
    add check (embedding_locked_at is null or embedding_source_id is not null),
    add check ((vision_source_id is null) = (vision_upstream_model_id is null)),
    add foreign key (organization_id, embedding_source_id, embedding_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred,
    add foreign key (organization_id, vision_source_id, vision_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred;

-- The lock is a corpus fact: no policy write changes or releases it, and the policy
-- cannot disappear while its organization exists (organization deletion cascades).
create function keep_locked_embedding() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        if old.embedding_locked_at is not null
           and exists (select 1 from space where id = old.organization_id) then
            raise exception 'the indexed corpus keeps its embedding model' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        return old;
    end if;
    if old.embedding_locked_at is not null
       and (new.embedding_source_id, new.embedding_upstream_model_id, new.embedding_locked_at)
           is distinct from (old.embedding_source_id, old.embedding_upstream_model_id, old.embedding_locked_at) then
        raise exception 'the indexed corpus keeps its embedding model' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;
create trigger organization_embedding_locked before update or delete on organization_model_policy
    for each row execute function keep_locked_embedding();
comment on trigger organization_embedding_locked on organization_model_policy is
    'assertion: immutability - the indexed corpus embedding model';

-- Knowledge Flow's per-request models, by working space: the locked corpus embedding
-- (query embedding) and the organization's default chat model (document tools). The
-- connection is the approved reference, never a secret; revisions identify the facts.
-- `available` is the worker's stage admission (model_catalog::instance::admit_document):
-- an enabled source observed at its current revision, a present offer with the aptitude
-- of its use (`chat` or the attested `embedding` metadata); the policy's foreign keys
-- already require the permission and its source assignment. A failed discovery keeps
-- the last observed offers, as for every admission; a withdrawal removes them.
create view cp_read.organization_model as
select s.id as space_id, p.organization_id, u.use, u.source_id, u.upstream_model_id,
       m.configuration->'inference' as connection,
       (m.configuration->>'revision')::bigint as source_revision,
       m.snapshot_revision, p.revision as policy_revision,
       coalesce((m.configuration->>'enabled')::boolean, false)
           and m.snapshot_source_revision is not distinct from (m.configuration->>'revision')::bigint
           and coalesce(o.advertised, false)
           and coalesce(o.metadata -> u.use = 'true'::jsonb, false) as available
from space s
join organization_model_policy p on p.organization_id = s.organization_id
cross join lateral (values
    ('embedding', p.embedding_source_id, p.embedding_upstream_model_id, p.embedding_locked_at is not null),
    ('chat', p.default_source_id, p.default_upstream_model_id, true)
) as u(use, source_id, upstream_model_id, applies)
join model_source m on m.source_id = u.source_id
left join model_offer o on o.source_id = u.source_id and o.upstream_model_id = u.upstream_model_id
where u.applies;
-- space_id/use select the row; `use` also names the aptitude in the offer metadata.
grant select on cp_read.organization_model to fred_kf_reader;
