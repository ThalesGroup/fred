-- Test fixture constructor: exercise the same immutable-content constraints as production.
create function fixture_document(p_id uuid,p_space_id uuid,p_name text,p_mime text,p_size bigint,
    p_sha256 text,p_created_by text,p_object_key text,p_quota_owner uuid,
    p_folder_id uuid default null,p_session_id uuid default null,
    p_created_at timestamptz default now(),p_retrievable boolean default false) returns uuid
language plpgsql as $$
declare org uuid;
begin
    select organization_id into org from space where id=p_quota_owner;
    insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes)
        values(org,'organization_total',9223372036854775807,0,0),(p_quota_owner,'local',9223372036854775807,0,0)
        on conflict do nothing;
    insert into document(id,space_id,folder_id,session_id,name,created_by,created_at,quota_owner,retrievable)
        values(p_id,p_space_id,p_folder_id,p_session_id,p_name,p_created_by,p_created_at,p_quota_owner,p_retrievable);
    insert into document_content(id,document_id,kind,mime,size,sha256,object_key,published_at)
        values(p_id,p_id,'primary',p_mime,p_size,p_sha256,p_object_key,now());
    update document set current_content_id=p_id where id=p_id;
    return p_id;
end $$;
