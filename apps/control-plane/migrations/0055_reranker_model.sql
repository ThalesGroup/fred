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

create or replace function model_use_options(metadata jsonb) returns jsonb
    language sql immutable strict as $$
    with reported as (
        select metadata->'chat' as chat,
               metadata->'embedding' as embedding,
               metadata->'vision' as vision,
               metadata->'rerank' as rerank,
               coalesce(nullif(metadata->'audio_transcription', 'null'::jsonb),
                        metadata->'provider_capabilities'->'audio_transcription') as transcription
    ), classified as (
        select *, not coalesce('true'::jsonb in (chat, embedding, vision, transcription, rerank), false)
            and not exists (
                select 1 from unnest(array['completion_fim', 'classification', 'ocr',
                    'audio_transcription_realtime', 'audio_generation', 'speech_generation']) as capability(name)
                where metadata->'provider_capabilities'->capability.name = 'true'::jsonb
            ) as unverified
        from reported
    ), options as (
        select unverified, vision, rerank,
               coalesce(chat='true'::jsonb, false) or
                   (unverified and chat is distinct from 'false'::jsonb) as can_chat,
               coalesce(embedding='true'::jsonb, false) or
                   (unverified and embedding is distinct from 'false'::jsonb) as can_embed,
               coalesce(transcription='true'::jsonb, false) or
                   (unverified and transcription is distinct from 'false'::jsonb) as can_transcribe
        from classified
    )
    select jsonb_build_object('unverified', unverified, 'chat', can_chat, 'embedding', can_embed,
        'vision', can_chat and vision is distinct from 'false'::jsonb, 'transcription', can_transcribe,
        'rerank', coalesce(rerank='true'::jsonb, false))
    from options
$$;
revoke execute on function model_use_options(jsonb) from public;
grant execute on function model_use_options(jsonb) to fred_kf_reader;

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
    ('chat', p.default_source_id, p.default_upstream_model_id, true),
    ('rerank', p.reranker_source_id, p.reranker_upstream_model_id, true)
) as u(use, source_id, upstream_model_id, applies)
join model_source m on m.source_id = u.source_id
left join organization_model_catalog c on c.source_id=m.source_id and c.organization_id=p.organization_id and c.deleted_at is null
left join model_offer o on o.source_id = u.source_id and o.upstream_model_id = u.upstream_model_id
where u.applies;
-- space_id/use select the row; use also names the aptitude in the offer metadata.
grant select on cp_read.organization_model to fred_kf_reader;
