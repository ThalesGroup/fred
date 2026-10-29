-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

with documents as materialized (
    select d.id, d.space_id, d.size, d.published_generation,
           d.deletion_id is null and s.deletion_id is null as active
    from document d join space s on s.id = d.space_id
    where s.organization_id = $1
      and ($2::uuid is null or s.id = $2 or s.parent_id = $2)
      -- Conversation attachments are private to their owner, so absent from every count.
      and d.session_id is null
), publications as (
    -- The official generation, independently of the last attempt's status.
    select d.id as document_id, cardinality(g.vector_ordinals) as vectors, g.rows,
           count(*) filter (where a.path like 'datasets/%.parquet') as datasets
    from documents d
    join generation g on g.id = d.published_generation
    left join artifact a on a.generation_id = g.id
    where d.active
    group by d.id, g.id
)
select d.space_id,
       count(*) filter (where d.active) as documents,
       coalesce(sum(d.size) filter (where d.active), 0)::bigint as bytes,
       count(*) filter (where not d.active) as purge_documents,
       coalesce(sum(d.size) filter (where not d.active), 0)::bigint as purge_bytes,
       count(p.document_id) as published_documents,
       coalesce(sum(p.vectors), 0)::bigint as chunks,
       coalesce(sum(p.vectors), 0)::bigint as vectors,
       coalesce(sum(p.datasets), 0)::bigint as datasets,
       coalesce(sum(p.rows) filter (where p.datasets = 1 and p.rows is not null), 0)::bigint as known_rows,
       coalesce(sum(p.datasets) filter (where p.datasets <> 1 or p.rows is null), 0)::bigint as unknown_datasets
from documents d left join publications p on p.document_id = d.id
group by d.space_id
