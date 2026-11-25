// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

async fn setup_source() -> (Documents, Arc<Processing>, Uuid, Uuid) {
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    let (mut d, p) = setup_with_lifecycle(lifecycle.clone()).await;
    let instance = Uuid::new_v4();
    let run = Uuid::new_v4();
    sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised) values('fixture','knowledge-base:test','1','{}',true)").execute(&d.e.pool).await.unwrap();
    sqlx::query(
        "insert into kb_definition(id,runtime_id,config_schema) values('test','fixture','{}')",
    )
    .execute(&d.e.pool)
    .await
    .unwrap();
    sqlx::query("insert into kb_instance(id,definition_id,space_id,folder_id,config,credential_refs,profile,created_by) values($1,'test',$2,$3,'{}','{}','fast','writer')")
        .bind(instance).bind(d.folder.space_id).bind(d.folder.id).execute(&d.e.pool).await.unwrap();
    sqlx::query("insert into kb_run(id,instance_id,runtime_id,definition_id,space_id,folder_id,config,credential_refs,profile,request_key,requested_by,workflow_id,task_queue) values($1,$2,'fixture','test',$3,$4,'{}','{}','fast','first','writer',$1::text,'fixture')")
        .bind(run).bind(instance).bind(d.folder.space_id).bind(d.folder.id).execute(&d.e.pool).await.unwrap();
    let mut platform = control_plane::agents::PlatformConfig::default();
    platform.knowledge_bases.workers.insert(
        "fixture".into(),
        control_plane::processing::config::WorkerIdentity {
            issuer: d.identity.realm.clone(),
            audience: "app".into(),
            client_id: "kb-worker".into(),
        },
    );
    d.app = api::router(
        api::AppState {
            history: None,
            agent_catalog: platform,
            pool: d.e.pool.clone(),
            auth: Arc::new(d.identity.auth().await),
            content: Some(d.storage.clone()),
            processing: Some(p.clone()),
            directory: None,
            onboarding: Default::default(),
            lifecycle,
        },
        "/v1",
        &[],
    );
    (d, p, instance, run)
}
async fn worker_request(
    d: &Documents,
    method: &str,
    path: &str,
    body: Vec<u8>,
    multipart: bool,
    key: Option<Uuid>,
) -> (u16, Value) {
    let now = chrono::Utc::now().timestamp();
    let token=d.identity.sign(json!({"sub":"kb-worker-subject","preferred_username":"service-account-kb-worker","iss":d.identity.realm,"aud":"app","azp":"kb-worker","client_id":"kb-worker","iat":now,"exp":now+600}));
    let mut request = Request::builder()
        .method(method)
        .uri(format!("/v1{path}"))
        .header("authorization", format!("Bearer {token}"));
    if multipart {
        request = request.header("content-type", "multipart/form-data; boundary=fixture");
    }
    if let Some(key) = key {
        request = request.header("idempotency-key", key.to_string());
    }
    json_response(
        d.app
            .clone()
            .oneshot(request.body(Body::from(body)).unwrap())
            .await
            .unwrap(),
    )
    .await
}
async fn upload_source(
    d: &Documents,
    run: Uuid,
    version: &str,
    key: Uuid,
    bytes: &[u8],
) -> (u16, Value) {
    let mut body=b"--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"source.txt\"\r\nContent-Type: text/plain\r\n\r\n".to_vec();
    body.extend_from_slice(bytes);
    body.extend_from_slice(b"\r\n--fixture--\r\n");
    worker_request(
        d,
        "POST",
        &format!("/knowledge-base-runs/{run}/documents?source_key=item&source_version={version}"),
        body,
        true,
        Some(key),
    )
    .await
}
async fn finish_source(p: &Processing, task: Uuid) {
    let row = store::row(&p.pool, task).await.unwrap();
    let work = row.work(p.installation);
    for stage in [Stage::Preparation, Stage::Extraction] {
        let descriptor = p
            .claim(claim(&work, stage, Uuid::new_v4(), 1))
            .await
            .unwrap();
        commit(p, &descriptor, &[("policy.json", b"{}")], 0).await;
    }
    let descriptor = p
        .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(
        p,
        &descriptor,
        &[("output.md", b"result"), ("metadata.json", b"{}")],
        0,
    )
    .await;
}
fn task(receipt: &Value) -> Uuid {
    Uuid::parse_str(receipt["task_id"].as_str().unwrap()).unwrap()
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn knowledge_base_replacement_retains_publication_and_retries_with_new_transfer() {
    let (d, p, instance, run) = setup_source().await;
    let key = Uuid::new_v4();
    let (status, first) = upload_source(&d, run, "v1", key, b"old").await;
    assert_eq!(status, 202, "{first}");
    let document = Uuid::parse_str(first["document_id"].as_str().unwrap()).unwrap();
    assert_eq!(upload_source(&d, run, "v1", key, b"old").await.1, first);
    assert_eq!(upload_source(&d, run, "v2", key, b"old").await.0, 409);
    assert_eq!(
        upload_source(&d, run, "v1", Uuid::new_v4(), b"old").await.0,
        409
    );
    let current: Option<String> =
        sqlx::query_scalar("select current_version from kb_source_document where instance_id=$1")
            .bind(instance)
            .fetch_one(&p.pool)
            .await
            .unwrap();
    assert_eq!(current, None);
    finish_source(&p, task(&first)).await;
    let (status, second) = upload_source(&d, run, "v2", Uuid::new_v4(), b"replacement").await;
    assert_eq!(status, 202, "{second}");
    assert_eq!(second["document_id"], first["document_id"]);
    let (version,current,size,reserved):(String,Uuid,i64,i64)=sqlx::query_as("select k.current_version,d.current_content_id,c.size,b.reserved_bytes from kb_source_document k join document d on d.id=k.document_id join document_content c on c.id=d.current_content_id join storage_budget b on b.space_id=d.quota_owner and b.scope='local' where k.instance_id=$1")
        .bind(instance).fetch_one(&p.pool).await.unwrap();
    assert_eq!((version.as_str(), size, reserved), ("v1", 3, 8));
    sqlx::query("update document_processing set status='failed',error_code='fixture_failure',completed_at=clock_timestamp() where id=$1")
        .bind(task(&second)).execute(&p.pool).await.unwrap();
    let failed = store::row(&p.pool, task(&second)).await.unwrap();
    let retired: bool =
        sqlx::query_scalar("select cleanup_after is not null from document_content where id=$1")
            .bind(failed.content_id)
            .fetch_one(&p.pool)
            .await
            .unwrap();
    assert!(retired);
    let (status, retry) = upload_source(&d, run, "v2", Uuid::new_v4(), b"replacement").await;
    assert_eq!(status, 202, "{retry}");
    let retry_row = store::row(&p.pool, task(&retry)).await.unwrap();
    assert_ne!(retry_row.content_id, failed.content_id);
    assert_eq!(retry_row.expected_content_id, current);
    // A failed scan and a paused instance do not revoke its admitted document processing.
    sqlx::query("update kb_instance set paused=true where id=$1")
        .bind(instance)
        .execute(&p.pool)
        .await
        .unwrap();
    sqlx::query("update kb_run set state='failed',completed_at=clock_timestamp(),error_code='scan_failed' where id=$1").bind(run).execute(&p.pool).await.unwrap();
    let (status, replay) = worker_request(
        &d,
        "POST",
        &format!("/knowledge-base-runs/{run}/claim"),
        vec![],
        false,
        None,
    )
    .await;
    assert_eq!(status, 200, "{replay}");
    assert_eq!(replay["state"], "failed");
    assert_eq!(
        upload_source(&d, run, "v3", Uuid::new_v4(), b"later")
            .await
            .0,
        409
    );
    finish_source(&p, task(&retry)).await;
    let (version,content,size,reserved):(String,Uuid,i64,i64)=sqlx::query_as("select k.current_version,d.current_content_id,c.size,b.reserved_bytes from kb_source_document k join document d on d.id=k.document_id join document_content c on c.id=d.current_content_id join storage_budget b on b.space_id=d.quota_owner and b.scope='local' where k.instance_id=$1")
        .bind(instance).fetch_one(&p.pool).await.unwrap();
    assert_eq!(
        (version.as_str(), content, size, reserved),
        ("v2", retry_row.content_id, 11, 0)
    );
    assert!(
        p.start(
            "writer",
            Uuid::new_v4(),
            document,
            Start {
                profile: Profile::Fast,
                retry_of: None
            }
        )
        .await
        .is_err()
    );
    let (status, refusal) = d
        .json(
            "writer",
            "PUT",
            &format!("/documents/{document}/retrievable"),
            json!({"retrievable": false}),
        )
        .await;
    assert_eq!(status, 409, "{refusal}");
    assert_eq!(refusal["code"], "knowledge_base_managed");
    assert_eq!(
        d.upload("writer", "manual.txt", b"manual", Uuid::new_v4(), None)
            .await
            .0,
        409
    );
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/documents/{document}"),
            json!({})
        )
        .await
        .0,
        409
    );
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/folders/{}", d.folder.id),
            json!({})
        )
        .await
        .0,
        409
    );
    let (status, catalogue) = worker_request(
        &d,
        "GET",
        &format!("/knowledge-base-runs/{run}/documents"),
        vec![],
        false,
        None,
    )
    .await;
    assert_eq!(status, 200, "{catalogue}");
    assert_eq!(catalogue["items"][0]["current_version"], "v2");
    assert!(catalogue["items"][0]["pending_version"].is_null());
    let forged = Uuid::new_v4();
    assert_eq!(
        worker_request(
            &d,
            "GET",
            &format!("/knowledge-base-runs/{run}/documents/tasks/{forged}"),
            vec![],
            false,
            None
        )
        .await
        .0,
        404
    );
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn knowledge_base_explicit_retract_uses_document_retirement() {
    let (d, p, instance, run) = setup_source().await;
    assert_eq!(
        d.json(
            "writer",
            "GET",
            &format!("/knowledge-base-runs/{run}/documents"),
            json!({})
        )
        .await
        .0,
        403
    );
    let (status, receipt) = upload_source(&d, run, "v1", Uuid::new_v4(), b"old").await;
    assert_eq!(status, 202, "{receipt}");
    let path = format!("/knowledge-base-runs/{run}/documents?source_key=item");
    assert_eq!(
        worker_request(&d, "DELETE", &path, vec![], false, None)
            .await
            .0,
        409
    );
    finish_source(&p, task(&receipt)).await;
    assert_eq!(
        worker_request(&d, "DELETE", &path, vec![], false, None)
            .await
            .0,
        204
    );
    assert_eq!(
        worker_request(&d, "DELETE", &path, vec![], false, None)
            .await
            .0,
        204
    );
    let document = Uuid::parse_str(receipt["document_id"].as_str().unwrap()).unwrap();
    let detached: bool=sqlx::query_scalar("select document_id is null and current_version is null from kb_source_document where instance_id=$1")
        .bind(instance).fetch_one(&p.pool).await.unwrap();
    assert!(detached);
    let retired: bool =
        sqlx::query_scalar("select deletion_id is not null from document where id=$1")
            .bind(document)
            .fetch_one(&p.pool)
            .await
            .unwrap();
    assert!(retired);
    // Reappearance is independent of the retired original's retention deadline.
    let (status, new) = upload_source(&d, run, "v1", Uuid::new_v4(), b"old").await;
    assert_eq!(status, 202, "{new}");
    assert_ne!(new["document_id"], receipt["document_id"]);
    finish_source(&p, task(&new)).await;
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn knowledge_base_concurrent_run_replays_one_admission() {
    let (d, p, instance, run) = setup_source().await;
    sqlx::query("update kb_run set state='succeeded',completed_at=clock_timestamp() where id=$1")
        .bind(run)
        .execute(&p.pool)
        .await
        .unwrap();
    sqlx::query("insert into organization_capability(organization_id,source_id,capability_id,enabled_by) select organization_id,'fixture','knowledge-base:test','owner' from space where id=$1")
        .bind(d.folder.space_id).execute(&p.pool).await.unwrap();
    let path = format!("/knowledge-bases/{instance}/runs");
    let body = json!({"request_key":"concurrent-replay"});
    let (first, second) = tokio::join!(
        d.json("owner", "POST", &path, body.clone()),
        d.json("owner", "POST", &path, body),
    );
    assert_eq!(first.0, 202, "{}", first.1);
    assert_eq!(second.0, 202, "{}", second.1);
    assert_eq!(first.1["id"], second.1["id"]);
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from kb_run where instance_id=$1 and state='pending'"
        )
        .bind(instance)
        .fetch_one(&p.pool)
        .await
        .unwrap(),
        1
    );
    d.e.pool.close().await;
}
