-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

set local lock_timeout = '5s';

alter table organization_model_policy
    add column reranker_source_id text collate "C",
    add column reranker_upstream_model_id text collate "C",
    add check ((reranker_source_id is null) = (reranker_upstream_model_id is null)),
    add foreign key (organization_id, reranker_source_id, reranker_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred;

create or replace view cp_read.organization_model as
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
    ('chat', p.default_source_id, p.default_upstream_model_id, true),
    ('rerank', p.reranker_source_id, p.reranker_upstream_model_id, true)
) as u(use, source_id, upstream_model_id, applies)
join model_source m on m.source_id = u.source_id
left join model_offer o on o.source_id = u.source_id and o.upstream_model_id = u.upstream_model_id
where u.applies;
grant select on cp_read.organization_model to fred_kf_reader;
