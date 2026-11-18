// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use sqlx::PgPool;
#[path = "support/database.rs"]
mod database;

async fn fixture() -> PgPool {
    let pool = database::database().await;
    sqlx::raw_sql(
        r#"
create function process_content(doc uuid, content uuid) returns uuid language plpgsql as $$
declare result uuid:=gen_random_uuid();
begin
    insert into document_processing(id,request_key,actor,document_id,content_id,expected_content_id,
        expected_generation_id,profile,workflow_id,submission,deadline_at,profile_settings,
        preparation_seconds,extraction_seconds,indexing_seconds)
    select result,result,'alice',doc,content,current_content_id,published_generation,'fast',result::text,
        '{}',now()+interval '1 hour','{}',60,60,60 from document where id=doc;
    return result;
end $$;
create function publish_content(processing uuid) returns uuid language plpgsql as $$
declare result uuid:=gen_random_uuid(); doc uuid; content uuid;
begin
    select document_id,content_id into strict doc,content from document_processing where id=processing;
    insert into generation(id,processing_id,document_id,stage,execution_id,activity_id,attempt,
        expires_at,prefix,cleanup_after,committed_at,vector_ordinals,cleaned_at)
    values(result,processing,doc,'indexing',result,result,1,now()+interval '1 hour',result::text,
        now()+interval '2 hours',now(),'{}',now());
    update document_processing set status='succeeded',stage='done',completed_at=now() where id=processing;
    update document set current_content_id=content,published_generation=result where id=doc;
    return result;
end $$;
create function replacement(doc uuid, bytes bigint) returns uuid language plpgsql as $$
declare result uuid:=gen_random_uuid();
begin
    insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at)
        values(result,doc,'primary',result::text,'text/plain',bytes,repeat('b',64),now());
    insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,session_id,
        quota_owner,name,mime,size,sha256,object_key,status,expires_at,completed_at,
        target_document_id,content_id,expected_content_id,reserved_bytes)
    select result,result,'alice',s.organization_id,d.space_id,d.folder_id,d.session_id,d.quota_owner,
        d.name,'text/plain',bytes,repeat('b',64),result::text,'stored',now()+interval '1 hour',now(),
        doc,result,d.current_content_id,greatest(bytes-c.size,0)
    from document d join document_content c on c.id=d.current_content_id join space s on s.id=d.space_id
    where d.id=doc;
    return result;
end $$;
create function source_document() returns uuid language plpgsql as $$
declare org uuid:=gen_random_uuid(); folder uuid:=gen_random_uuid(); doc uuid:=gen_random_uuid();
begin
    insert into space(id,kind,name,organization_id) values(org,'organization',org::text,org);
    insert into folder(id,space_id,name,path) values(folder,org,'files','/'||folder::text||'/');
    perform fixture_document(doc,org,doc::text,'text/plain',10,repeat('a',64),'alice',doc::text,org,folder);
    update storage_budget set limit_bytes=100 where space_id=org;
    return doc;
end $$;
"#,
    )
    .execute(&pool)
    .await
    .unwrap();
    pool
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL"]
async fn replacement_preserves_old_publication_and_charges_only_growth() {
    let pool = fixture().await;
    sqlx::raw_sql(
        r#"
do $$
declare doc uuid:=source_document(); first uuid; candidate uuid; processing uuid; next_generation uuid;
begin
    first:=publish_content(process_content(doc,doc));
    candidate:=replacement(doc,30);
    processing:=process_content(doc,candidate);
    if not exists(select 1 from document where id=doc and current_content_id=doc and published_generation=first)
        or exists(select 1 from storage_budget where used_bytes<>10 or reserved_bytes<>20) then
        raise exception 'candidate changed the usable publication or reserved more than growth';
    end if;
    begin
        update document_upload set reserved_bytes=0 where content_id=candidate;
        raise exception 'premature reservation release accepted';
    exception when check_violation then null;
    end;
    begin
        update document set current_content_id=candidate where id=doc;
        raise exception 'unprocessed source replacement accepted';
    exception when check_violation then null;
    end;
    begin
        perform process_content(doc,doc);
        raise exception 'concurrent processing accepted';
    exception when unique_violation then null;
    end;
    next_generation:=publish_content(processing);
    if not exists(select 1 from document where id=doc and current_content_id=candidate and published_generation=next_generation)
        or exists(select 1 from storage_budget where used_bytes<>30 or reserved_bytes<>0)
        or not exists(select 1 from generation where id=first and cleaned_at is null and cleanup_cursor=0)
        or not exists(select 1 from document_content where id=doc and cleanup_after is not null) then
        raise exception 'replacement did not atomically swap, account or retire';
    end if;
    begin
        update document set current_content_id=doc,published_generation=first where id=doc;
        raise exception 'historical publication rollback accepted';
    exception when check_violation then null;
    end;
    -- A second successful processing of exactly the current bytes is valid.
    perform publish_content(process_content(doc,candidate));
    if (select count(*) from document_processing where document_id=doc and status='succeeded')<>3 then
        raise exception 'successful processing history was lost';
    end if;
    if exists(select 1 from storage_budget where used_bytes<>30 or reserved_bytes<>0) then
        raise exception 'reprocessing charged originals again';
    end if;
end $$;
"#,
    )
    .execute(&pool)
    .await
    .unwrap();
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL"]
async fn failed_or_stale_candidates_never_replace_the_published_source() {
    let pool = fixture().await;
    sqlx::raw_sql(
        r#"
do $$
declare doc uuid:=source_document(); first uuid; candidate uuid; processing uuid; other uuid;
begin
    first:=publish_content(process_content(doc,doc));
    candidate:=replacement(doc,40);
    processing:=process_content(doc,candidate);
    update document_processing set status='failed',completed_at=now() where id=processing;
    if not exists(select 1 from document where id=doc and current_content_id=doc and published_generation=first)
        or exists(select 1 from storage_budget where used_bytes<>10 or reserved_bytes<>0)
        or not exists(select 1 from document_content where id=candidate and cleanup_after is not null) then
        raise exception 'failure changed publication, leaked reservation or missed cleanup';
    end if;
    begin
        perform process_content(doc,candidate);
        raise exception 'cleanup candidate readmitted';
    exception when check_violation then null;
    end;
    begin
        update document_content set cleanup_after=null where id=candidate;
        raise exception 'cleanup fence reversed';
    exception when check_violation then null;
    end;
    other:=process_content(doc,doc);
    begin
        update document_processing set content_id=candidate where id=other;
        raise exception 'processing source mutated';
    exception when check_violation then null;
    end;
    perform publish_content(other);
    begin
        update document set published_generation=first where id=doc;
        raise exception 'same-content stale generation published';
    exception when check_violation then null;
    end;
    begin
        perform replacement(doc,101);
        raise exception 'over-quota candidate accepted';
    exception when sqlstate 'FR001' then null;
    end;
end $$;
"#,
    )
    .execute(&pool)
    .await
    .unwrap();
}
