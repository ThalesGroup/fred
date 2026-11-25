-- Each fact keeps its original identity and lifecycle. No acknowledgement filter:
-- dismissing an upload from its personal panel does not erase team history.
with activity as (
    select u.id, 'upload'::text as kind,
        case u.status when 'stored' then 'succeeded' when 'pending' then 'running' else 'failed' end as status,
        u.target_document_id as target_id, u.name, null::text as stage,
        u.processing_profile as profile, u.error_code, u.created_at,
        null::timestamptz as due_at, u.completed_at, u.retry_of
    from document_upload u
    where u.space_id=$1 and u.organization_id=$2 and u.session_id is null and u.purpose='source'
    union all
    select p.id, 'processing', p.status, d.id, d.name, p.stage, p.profile,
        p.error_code, p.created_at, null::timestamptz, p.completed_at, p.retry_of
    from document_processing p join document d on d.id=p.document_id
    where d.space_id=$1 and d.session_id is null
    union all
    select r.id, case r.target_kind when 'document' then 'document_deletion' else 'folder_deletion' end,
        case r.status when 'queued' then 'pending' when 'completed' then 'succeeded' else r.status end,
        r.target_id, null::text, null::text, null::text, r.error_code,
        r.requested_at, r.due_at, r.completed_at, null::uuid
    from deletion r
    where r.target_parent_id=$1 and r.organization_id=$2
        and r.target_kind in ('document','folder') and r.document_session_id is null
)
select * from activity
where created_at <= $3
    and ($4::text is null or kind=$4)
    and ($5::text is null or status=$5)
    and ($6::timestamptz is null or (created_at,id,kind)<($6,$7,$8::text))
order by created_at desc,id desc,kind desc
limit 51
