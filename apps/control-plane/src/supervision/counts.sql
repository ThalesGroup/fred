-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

with documents as materialized (
    select d.id, d.space_id, d.size,
           d.deletion_id is null and s.deletion_id is null as active
    from document d join space s on s.id = d.space_id
    where s.organization_id = $1
      and ($2::uuid is null or s.id = $2 or s.parent_id = $2)
), publications as (
    -- The unique success, independently of the last attempt's status.
    select p.document_id, p.chunks, p.vectors, p.rows,
           count(a.value) filter (
               where a.value->>'path' like 'datasets/%.parquet'
           ) as datasets
    from document_processing p
    join documents d on d.id = p.document_id and d.active
    left join lateral jsonb_array_elements(p.manifest->'artifacts') a(value) on true
    where p.status = 'succeeded'
    group by p.id
)
select d.space_id,
       count(*) filter (where d.active) as documents,
       coalesce(sum(d.size) filter (where d.active), 0)::bigint as bytes,
       count(*) filter (where not d.active) as purge_documents,
       coalesce(sum(d.size) filter (where not d.active), 0)::bigint as purge_bytes,
       count(p.document_id) as published_documents,
       coalesce(sum(p.chunks), 0)::bigint as chunks,
       coalesce(sum(p.vectors), 0)::bigint as vectors,
       coalesce(sum(p.datasets), 0)::bigint as datasets,
       coalesce(sum(p.rows) filter (where p.datasets = 1 and p.rows is not null), 0)::bigint as known_rows,
       coalesce(sum(p.datasets) filter (where p.datasets <> 1 or p.rows is null), 0)::bigint as unknown_datasets
from documents d left join publications p on p.document_id = d.id
group by d.space_id
