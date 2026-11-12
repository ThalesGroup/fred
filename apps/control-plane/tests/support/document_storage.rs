// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use crate::content_bucket::Bucket;
use aws_sdk_s3::primitives::ByteStream;
use sha2::{Digest, Sha256};
use std::time::Duration;
use uuid::Uuid;

#[tokio::test]
#[ignore = "needs disposable SeaweedFS: make test-integration"]
async fn seaweed_original_contract() {
    let b = Bucket::start().await;
    b.store.validate_bucket().await.unwrap();
    let file = tempfile::NamedTempFile::new().unwrap();
    let bytes = b"original content\n".repeat(4000);
    std::fs::write(file.path(), &bytes).unwrap();
    let hash: [u8; 32] = Sha256::digest(&bytes).into();
    b.store
        .put_verified("fixture/first", file.path(), bytes.len() as i64, &hash)
        .await
        .unwrap();
    b.store
        .put_verified("fixture/first", file.path(), bytes.len() as i64, &hash)
        .await
        .unwrap();
    let conflict = b
        .client
        .put_object()
        .bucket("originals")
        .key("fixture/first")
        .if_none_match("*")
        .body(ByteStream::from_static(b"replacement"))
        .send()
        .await;
    assert_eq!(
        conflict
            .unwrap_err()
            .raw_response()
            .unwrap()
            .status()
            .as_u16(),
        412
    );
    b.store
        .verify("fixture/first", bytes.len() as i64, &hash)
        .await
        .unwrap();
    assert!(
        b.store
            .verify("fixture/first", bytes.len() as i64, &[0; 32])
            .await
            .is_err()
    );
    b.store
        .put_verified("fixture/second", file.path(), bytes.len() as i64, &hash)
        .await
        .unwrap();
    let page = b.store.list("fixture/", None, 1).await.unwrap();
    assert_eq!(page.objects.len(), 1);
    assert!(page.next.is_some());
    let next = b.store.list("fixture/", page.next, 1).await.unwrap();
    assert_eq!(next.objects.len(), 1);
    assert_ne!(page.objects[0].0, next.objects[0].0);
    b.store.delete("fixture/first").await.unwrap();
    b.store.delete("fixture/first").await.unwrap();
    assert!(b.store.get("fixture/first").await.is_err());
    b.store
        .verify("fixture/second", bytes.len() as i64, &hash)
        .await
        .unwrap();
    assert_eq!(b.config.bucket, "originals");
    use aws_sdk_s3::types::{
        BucketLifecycleConfiguration, ExpirationStatus, LifecycleExpiration, LifecycleRule,
    };
    b.client
        .put_bucket_lifecycle_configuration()
        .bucket("originals")
        .lifecycle_configuration(
            BucketLifecycleConfiguration::builder()
                .rules(
                    LifecycleRule::builder()
                        .id("unsafe-expiration")
                        .status(ExpirationStatus::Enabled)
                        .filter(
                            aws_sdk_s3::types::LifecycleRuleFilter::builder()
                                .prefix("")
                                .build(),
                        )
                        .expiration(LifecycleExpiration::builder().days(1).build())
                        .build()
                        .unwrap(),
                )
                .build()
                .unwrap(),
        )
        .send()
        .await
        .unwrap();
    assert!(b.store.validate_bucket().await.is_err());
}

use axum::{
    Router,
    body::{Body, to_bytes},
    http::{Request, Response},
};
use control_plane::{
    api, db,
    documents::Storage,
    domain::{Folder, Role},
};
use serde_json::{Value, json};
use std::sync::Arc;
use tower::ServiceExt;

struct Documents {
    e: crate::Env,
    bucket: Bucket,
    identity: crate::support::IdentityServer,
    proxy: S3Proxy,
    storage: Arc<Storage>,
    app: Router,
    folder: Folder,
    _spool: tempfile::TempDir,
    _pod: PreparationPod,
}
struct PreparationPod {
    base: String,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for PreparationPod {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl PreparationPod {
    async fn start() -> Self {
        let app = Router::new().route(
            "/agents/capabilities/ppt_builder/validate-config",
            axum::routing::post(|body: axum::body::Bytes| async move {
                if body.windows(6).any(|part| part == b"reject") {
                    (
                        axum::http::StatusCode::UNPROCESSABLE_ENTITY,
                        axum::Json(json!({"detail":"Unreadable test template"})),
                    )
                } else {
                    (
                        axum::http::StatusCode::OK,
                        axum::Json(json!({"schema_version":"1","config":{"use_vision":false}})),
                    )
                }
            }),
        );
        let app=app.route("/agents/templates",axum::routing::get(|| async {axum::Json(json!([{
            "template_agent_id":"assistant","title":"Assistant","description":"Test","kind":"react","supports_capabilities":true,
            "default_capability_ids":["ppt_builder"],"available_capabilities":[{"id":"ppt_builder","kind":"tool","config_fields":[]}],
            "default_tuning":{"role":"Assistant","description":"Test","usage_statement":"Test","tags":[],"values":{},"fields":[]}
        }]))}));
        let app=app.route("/agents/templates/assistant/export-tuning",axum::routing::post(|| async {axum::Json(json!({"values":{}}))}))
            .route("/agents/capabilities/ppt_builder/export-config",axum::routing::post(|axum::Json(body):axum::Json<Value>| async move {
                assert!(body["config"]["config"]["analysis_id"].is_string());
                axum::Json(json!({"schema_version":"1","config":{"template_key":"template.pptx","use_vision":false},"files":{"template.pptx":body["files_by_slot"]["template"][0]}}))
            }))
            .route("/agents/capabilities/ppt_builder/copy-config",axum::routing::post(|axum::Json(body):axum::Json<Value>| async move {
                assert!(body.get("source_space_id").is_none());
                assert!(body["asset_files"]["template.pptx"].is_string());
                axum::Json(json!({"schema_version":"1","config":{"use_vision":false},"notices":[]}))
            }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Self { base, task }
    }
}
impl Documents {
    async fn start(quota: i64) -> Self {
        Self::start_spool(quota, false).await
    }
    async fn start_spool(quota: i64, root_owned: bool) -> Self {
        Self::start_with_limits(quota, root_owned, Default::default()).await
    }
    async fn start_with_limits(
        quota: i64,
        root_owned: bool,
        limits: control_plane::documents::config::Limits,
    ) -> Self {
        let e = crate::env().await;
        let (org, team) = crate::org_and_team(&e).await;
        for (user, role) in [
            ("writer", Role::Editor),
            ("reader", Role::Member),
            ("analyst", Role::Analyst),
            ("owner", Role::Owner),
        ] {
            crate::grant(&e, org.id, Role::Member, user).await;
            crate::grant(&e, team.id, role, user).await;
        }
        let folder = Folder {
            id: Uuid::new_v4(),
            space_id: team.id,
            parent_id: None,
            name: "Originals".into(),
            path: String::new(),
            created_at: chrono::Utc::now(),
        };
        let folder = Folder {
            path: control_plane::domain::folder_path(None, folder.id),
            ..folder
        };
        db::insert_folder(&e.pool, &folder).await.unwrap();
        let bucket = Bucket::start().await;
        let spool = tempfile::tempdir().unwrap();
        if root_owned {
            let volume = format!("{}:/spool", spool.path().display());
            assert!(
                std::process::Command::new("docker")
                    .args([
                        "run",
                        "--rm",
                        "--entrypoint",
                        "sh",
                        "-v",
                        &volume,
                        "chrislusf/seaweedfs:4.29",
                        "-c",
                        "chown 0:0 /spool && chmod 0777 /spool"
                    ])
                    .status()
                    .unwrap()
                    .success()
            );
            use std::os::unix::fs::MetadataExt;
            assert_eq!(std::fs::metadata(spool.path()).unwrap().uid(), 0);
        }
        let mut config = bucket.config.clone();
        config.limits = limits;
        let proxy = S3Proxy::start(config.endpoint.clone()).await;
        config.endpoint = proxy.endpoint.clone();
        config.limits.s3_seconds = 5;
        config.limits.idle_seconds = 2;
        config.limits.transfer_seconds = 2;
        config.limits.downloads = 1;
        config.temp_dir = spool.path().to_str().unwrap().into();
        config.limits.team_bytes = quota;
        config.limits.file_bytes = 1024 * 1024;

        let storage = Storage::start(
            &e.pool,
            None,
            config,
            "fixture-access".into(),
            "fixture-secret".into(),
        )
        .await
        .unwrap();
        let identity = crate::support::IdentityServer::start().await;
        let pod = PreparationPod::start().await;
        let mut platform = control_plane::agents::PlatformConfig::default();
        platform
            .runtime_catalog_sources
            .push(control_plane::agents::RuntimeCatalogSource {
                runtime_id: "fixture".into(),
                base_url: pod.base.clone(),
                public_base_url: Some("/fixture/v1".into()),
                enabled: true,
            });
        platform.capability_preparation.workers.insert(
            "fixture".into(),
            control_plane::processing::config::WorkerIdentity {
                issuer: identity.realm.clone(),
                audience: "app".into(),
                client_id: "preparation-worker".into(),
            },
        );
        for statement in [
            "insert into runtime_catalog(runtime_id,reachable) values('fixture',true)",
            "insert into capability_offer(source_id,capability_id,version,descriptor,advertised) values('fixture','ppt_builder','1','{}',true)",
            "insert into organization_capability(organization_id,source_id,capability_id,enabled_by) values($1,'fixture','ppt_builder','writer')",
        ] {
            let query = sqlx::query(statement);
            if statement.contains("$1") {
                query.bind(org.id).execute(&e.pool).await.unwrap();
            } else {
                query.execute(&e.pool).await.unwrap();
            }
        }
        let app = api::router(
            api::AppState {
                agent_catalog: platform,
                pool: e.pool.clone(),
                auth: Arc::new(identity.auth().await),
                content: Some(storage.clone()),
                processing: None,
                directory: None,
                onboarding: Default::default(),
                lifecycle: Default::default(),
            },
            "/v1",
            &[],
        );
        Self {
            e,
            bucket,
            identity,
            proxy,
            storage,
            app,
            folder,
            _spool: spool,
            _pod: pod,
        }
    }
    async fn request(
        &self,
        user: &str,
        method: &str,
        path: &str,
        body: Body,
        content_type: &str,
        key: Option<Uuid>,
    ) -> Response<Body> {
        let mut request = Request::builder()
            .method(method)
            .uri(format!("/v1{path}"))
            .header(
                "authorization",
                format!("Bearer {}", self.identity.token(user)),
            )
            .header("content-type", content_type);
        if let Some(key) = key {
            request = request.header("idempotency-key", key.to_string());
        }
        self.app
            .clone()
            .oneshot(request.body(body).unwrap())
            .await
            .unwrap()
    }
    async fn upload(
        &self,
        user: &str,
        name: &str,
        bytes: &[u8],
        key: Uuid,
        retry: Option<Uuid>,
    ) -> (u16, Value) {
        let mut body=format!("--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: text/plain\r\n\r\n").into_bytes();
        body.extend_from_slice(bytes);
        body.extend_from_slice(b"\r\n--fixture--\r\n");
        let path = format!(
            "/folders/{}/documents{}",
            self.folder.id,
            retry
                .map(|id| format!("?retry_of={id}"))
                .unwrap_or_default()
        );
        json_response(
            self.request(
                user,
                "POST",
                &path,
                Body::from(body),
                "multipart/form-data; boundary=fixture",
                Some(key),
            )
            .await,
        )
        .await
    }
    async fn json(&self, user: &str, method: &str, path: &str, value: Value) -> (u16, Value) {
        json_response(
            self.request(
                user,
                method,
                path,
                Body::from(value.to_string()),
                "application/json",
                None,
            )
            .await,
        )
        .await
    }
}
async fn json_response(response: Response<Body>) -> (u16, Value) {
    let status = response.status().as_u16();
    let bytes = to_bytes(response.into_body(), 2 * 1024 * 1024)
        .await
        .unwrap();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or_else(|_| json!(String::from_utf8_lossy(&bytes))),
    )
}

// Proves: I2, I3, I22
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_contract_guards_and_shared_project_quota() {
    let d = Documents::start_spool(8, true).await;
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let private = std::fs::metadata(d._spool.path().join("private")).unwrap();
    assert_ne!(private.uid(), 0);
    assert_eq!(private.permissions().mode() & 0o777, 0o700);
    let endpoint = format!("/folders/{}/documents", d.folder.id);
    for (body, content_type, expected) in [
        ("not multipart", "text/plain", 400),
        (
            "not multipart",
            "multipart/form-data; boundary=fixture",
            400,
        ),
        (
            "--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"one\"\r\n\r\nx\r\n--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"two\"\r\n\r\nx\r\n--fixture--\r\n",
            "multipart/form-data; boundary=fixture",
            422,
        ),
    ] {
        let response = d
            .request(
                "writer",
                "POST",
                &endpoint,
                Body::from(body),
                content_type,
                Some(Uuid::new_v4()),
            )
            .await;
        let (status, error) = json_response(response).await;
        assert_eq!(status, expected, "{error}");
        assert!(error["code"].is_string());
    }
    let response = d
        .request(
            "writer",
            "POST",
            &format!("{endpoint}/preflight"),
            Body::from("{"),
            "application/json",
            None,
        )
        .await;
    assert_eq!(response.status(), 400);
    assert_eq!(
        d.upload(
            "writer",
            "large",
            &vec![0; 1024 * 1024 + 1],
            Uuid::new_v4(),
            None
        )
        .await
        .0,
        413
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from document_upload")
            .fetch_one(&d.e.pool)
            .await
            .unwrap(),
        0
    );
    let project = control_plane::spaces::create_space(
        &d.e.pool,
        "alice",
        control_plane::domain::SpaceKind::Project,
        d.folder.space_id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    crate::grant(&d.e, project.id, Role::Editor, "writer").await;
    let folder = control_plane::spaces::create_folder(
        &d.e.pool,
        "writer",
        project.id,
        None,
        "Project folder".into(),
    )
    .await
    .unwrap();
    let project_endpoint = format!("/folders/{}/documents", folder.id);
    let body = "--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"project.txt\"\r\n\r\n12345\r\n--fixture--\r\n";
    let (team, project) = tokio::join!(
        d.upload("writer", "team.txt", b"12345", Uuid::new_v4(), None),
        d.request(
            "writer",
            "POST",
            &project_endpoint,
            Body::from(body),
            "multipart/form-data; boundary=fixture",
            Some(Uuid::new_v4())
        )
    );
    let mut statuses = [team.0, project.status().as_u16()];
    statuses.sort();
    assert_eq!(statuses, [201, 422]);
    let (_, summary) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{}/storage", d.folder.space_id),
            Value::Null,
        )
        .await;
    assert_eq!(summary["used_bytes"], 5);
    assert_eq!(summary["reserved_bytes"], 0);
    let (id, key): (Uuid, String) = sqlx::query_as("select id,object_key from document_current")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    d.bucket.store.delete(&key).await.unwrap();
    let response = d
        .request(
            "writer",
            "GET",
            &format!("/documents/{id}/content"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(response.status(), 503);
}

// Proves: I8, I22
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_publication_rechecks_token_and_terms_without_locking_remote_io() {
    let d = Arc::new(Documents::start(1024).await);
    for terms_case in [false, true] {
        let gate = Arc::new(crate::support::Gate::default());
        d.proxy.fault.lock().await.hold_put = Some(gate.clone());
        let mut app = d.app.clone();
        if terms_case {
            control_plane::onboarding::accept(&d.e.pool, Some("v1"), "writer", "v1")
                .await
                .unwrap();
            let storage = Storage::start(
                &d.e.pool,
                Some("v1".into()),
                d.storage.config.clone(),
                "fixture-access".into(),
                "fixture-secret".into(),
            )
            .await
            .unwrap();
            app = api::router(
                api::AppState {
                    agent_catalog: Default::default(),
                    pool: d.e.pool.clone(),
                    auth: Arc::new(d.identity.auth().await),
                    content: Some(storage),
                    processing: None,
                    directory: None,
                    onboarding: Default::default(),
                    lifecycle: Default::default(),
                },
                "/v1",
                &[],
            );
        }
        let now = chrono::Utc::now().timestamp();
        let token=d.identity.sign(json!({"sub":"writer","preferred_username":"writer","iss":d.identity.realm,"aud":"app","iat":now,"exp":now+if terms_case{300}else{2}}));
        let key = Uuid::new_v4();
        let body = format!(
            "--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{key}.txt\"\r\n\r\nbytes\r\n--fixture--\r\n"
        );
        let request = Request::builder()
            .method("POST")
            .uri(format!("/v1/folders/{}/documents", d.folder.id))
            .header("authorization", format!("Bearer {token}"))
            .header("idempotency-key", key.to_string())
            .header("content-type", "multipart/form-data; boundary=fixture")
            .body(Body::from(body))
            .unwrap();
        let sending = tokio::spawn(async move { app.oneshot(request).await.unwrap() });
        tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
            .await
            .unwrap();
        let org = control_plane::spaces::load(&d.e.pool, d.folder.space_id)
            .await
            .unwrap()
            .organization;
        let start = std::time::Instant::now();
        let lock = tokio::time::timeout(
            Duration::from_secs(1),
            crate::hold_organization_lock(&d.e, org),
        )
        .await
        .expect("S3 IO held the organization lock");
        println!(
            "document S3 gate: organization lock acquired in {:?}",
            start.elapsed()
        );
        lock.rollback().await.unwrap();
        if terms_case {
            sqlx::query("delete from terms_acceptance where user_id='writer'")
                .execute(&d.e.pool)
                .await
                .unwrap();
        } else {
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
        gate.release.notify_one();
        let (status, error) = json_response(sending.await.unwrap()).await;
        assert_eq!(status, if terms_case { 403 } else { 401 }, "{error}");
        assert_eq!(
            sqlx::query_scalar::<_, i64>("select count(*) from document")
                .fetch_one(&d.e.pool)
                .await
                .unwrap(),
            0
        );
    }
}

// Proves: I2, I3, I8, I22, I25
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_creation_reads_conflicts_receipts_and_safe_download() {
    let d = Documents::start(1024 * 1024).await;
    crate::support::member_organization(&d.e.pool, "Outside", "outsider")
        .await
        .unwrap();
    for user in ["reader", "analyst", "owner", "stranger", "outsider"] {
        let (status, body) = d
            .upload(user, "denied.txt", b"bytes", Uuid::new_v4(), None)
            .await;
        assert_eq!(
            status,
            if user == "outsider" { 404 } else { 403 },
            "{user}: {body}"
        );
        if user == "stranger" {
            assert_eq!(body["detail"], "user_not_admitted");
        }
    }
    let key = Uuid::new_v4();
    let bytes = b"unchanged original\n".repeat(9000);
    let (status, first) = d.upload("writer", "résumé.txt", &bytes, key, None).await;
    assert_eq!(status, 201, "{first}");
    assert_eq!(first["status"], "stored");
    let id = first["document_id"].as_str().unwrap();
    let (status, replay) = d
        .upload("writer", "re\u{301}sume\u{301}.txt", &bytes, key, None)
        .await;
    assert_eq!(status, 200, "{replay}");
    assert_eq!(replay["document_id"], id);
    let (status, error) = d
        .upload("writer", "résumé.txt", b"different", key, None)
        .await;
    assert_eq!(status, 409);
    assert_eq!(error["code"], "idempotency_conflict");
    let (status, error) = d
        .upload("writer", "résumé.txt", &bytes, Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 409);
    assert_eq!(error["code"], "name_conflict");
    let content = d
        .request(
            "reader",
            "GET",
            &format!("/documents/{id}/content"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(content.status(), 200);
    assert_eq!(
        content.headers()["content-type"],
        "application/octet-stream"
    );
    assert_eq!(content.headers()["x-content-type-options"], "nosniff");
    assert!(
        content.headers()["content-disposition"]
            .to_str()
            .unwrap()
            .contains("filename*=UTF-8''")
    );
    assert_eq!(
        to_bytes(content.into_body(), 1024 * 1024).await.unwrap(),
        bytes
    );
    for user in ["owner", "stranger", "outsider"] {
        assert_eq!(
            d.json(
                user,
                "GET",
                &format!("/documents/{id}/content"),
                Value::Null
            )
            .await
            .0,
            if user == "outsider" { 404 } else { 403 }
        );
    }
    assert_eq!(
        d.json(
            "reader",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null
        )
        .await
        .0,
        404
    );
    let (status, page) = d
        .json(
            "reader",
            "GET",
            &format!(
                "/spaces/{}/entries?parent_id={}&limit=1",
                d.folder.space_id, d.folder.id
            ),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{page}");
    assert_eq!(page["total"], 1);
    assert_eq!(page["items"][0]["kind"], "document");
    assert_eq!(page["ancestors"][0]["id"], d.folder.id.to_string());
    let (status, stats) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{}/storage", d.folder.space_id),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{stats}");
    assert_eq!(stats["used_bytes"], bytes.len());
    assert_eq!(stats["reserved_bytes"], 0);
    let path = format!("/spaces/{}/document-uploads", d.folder.space_id);
    assert_eq!(
        d.json("writer", "GET", &path, Value::Null)
            .await
            .1
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        d.json(
            "writer",
            "PUT",
            &format!("/document-uploads/{key}/acknowledgment"),
            Value::Null
        )
        .await
        .0,
        204
    );
    assert!(
        d.json("writer", "GET", &path, Value::Null)
            .await
            .1
            .as_array()
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        d.json(
            "writer",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null
        )
        .await
        .0,
        200
    );
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/folders/{}", d.folder.id),
            Value::Null
        )
        .await
        .0,
        409
    );
    d.storage.cleanup_tick().await.unwrap();
    assert_eq!(
        d.request(
            "reader",
            "GET",
            &format!("/documents/{id}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );
    let (status, body) = d
        .json("writer", "GET", "/document-uploads/bad-id", Value::Null)
        .await;
    assert_eq!(status, 422);
    assert_eq!(body["code"], "invalid_fields");
    let (status, body) = d
        .json(
            "writer",
            "POST",
            &format!("/folders/{}/documents", d.folder.id),
            json!({}),
        )
        .await;
    assert_eq!(status, 422);
    assert_eq!(body["code"], "invalid_fields");
    let (_, preflight) = d
        .json(
            "writer",
            "POST",
            &format!("/folders/{}/documents/preflight", d.folder.id),
            json!({"files":[{"name":"résumé.txt","size":1}]}),
        )
        .await;
    assert_eq!(preflight["conflicts"], json!(["résumé.txt"]));
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_concurrent_names_and_quotas_have_one_winner() {
    let d = Documents::start(10).await;
    let (a, b) = tokio::join!(
        d.upload("writer", "a.txt", b"123456", Uuid::new_v4(), None),
        d.upload("writer", "b.txt", b"123456", Uuid::new_v4(), None)
    );
    let mut statuses = vec![a.0, b.0];
    statuses.sort();
    assert_eq!(statuses, vec![201, 422], "{a:?} {b:?}");
    let winner = if a.0 == 201 { "a.txt" } else { "b.txt" };
    let (a, b) = tokio::join!(
        d.upload("writer", "same.txt", b"1", Uuid::new_v4(), None),
        d.upload("writer", "same.txt", b"1", Uuid::new_v4(), None)
    );
    let mut statuses = vec![a.0, b.0];
    statuses.sort();
    assert_eq!(statuses, vec![201, 409], "{a:?} {b:?}");
    assert_eq!(
        d.upload("writer", winner, b"1", Uuid::new_v4(), None)
            .await
            .0,
        409
    );
    assert_eq!(
        d.upload(
            "writer",
            "big.txt",
            &vec![0; 1024 * 1024 + 1],
            Uuid::new_v4(),
            None
        )
        .await
        .0,
        413
    );
    assert_eq!(
        d.upload("writer", "../escape", b"1", Uuid::new_v4(), None)
            .await
            .0,
        422
    );
    assert_eq!(
        d.upload("writer", "empty.txt", b"", Uuid::new_v4(), None)
            .await
            .0,
        201
    );
}

#[derive(Default)]
struct S3Fault {
    hold_put: Option<Arc<crate::support::Gate>>,
    lose_put_ack: bool,
    deny_put: bool,
    deny_head_path: Option<String>,
}
struct S3Proxy {
    endpoint: String,
    fault: Arc<tokio::sync::Mutex<S3Fault>>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for S3Proxy {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl S3Proxy {
    async fn start(upstream: String) -> Self {
        let fault = Arc::new(tokio::sync::Mutex::new(S3Fault::default()));
        let state = fault.clone();
        let client = reqwest::Client::new();
        let app = Router::new().fallback(axum::routing::any(move |request: Request<Body>| {
            let state = state.clone();
            let client = client.clone();
            let upstream = upstream.clone();
            async move {
                let (parts, body) = request.into_parts();
                let is_put = parts.method == "PUT";
                let bytes = to_bytes(body, 2 * 1024 * 1024).await.unwrap();
                let (gate, lose, deny) = {
                    let mut s = state.lock().await;
                    (
                        if is_put { s.hold_put.take() } else { None },
                        is_put && s.lose_put_ack,
                        (is_put && s.deny_put)
                            || (parts.method == "HEAD"
                                && s.deny_head_path.as_deref() == Some(parts.uri.path())),
                    )
                };
                if let Some(gate) = gate {
                    gate.entered.notify_one();
                    gate.release.notified().await;
                }
                if deny {
                    return Response::builder().status(503).body(Body::empty()).unwrap();
                }
                let response = client
                    .request(parts.method, format!("{upstream}{}", parts.uri))
                    .headers(parts.headers)
                    .body(bytes)
                    .send()
                    .await
                    .unwrap();
                let status = response.status();
                let headers = response.headers().clone();
                let bytes = response.bytes().await.unwrap();
                if lose {
                    return Response::builder().status(503).body(Body::empty()).unwrap();
                }
                let mut response = Response::builder()
                    .status(status)
                    .body(Body::from(bytes))
                    .unwrap();
                *response.headers_mut() = headers;
                response
            }
        }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Self {
            endpoint,
            fault,
            task,
        }
    }
}

// Proves: I5, I8, I22, I25
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_revocation_cleanup_and_late_put_recovery() {
    let d = Arc::new(Documents::start(1024).await);
    let gate = Arc::new(crate::support::Gate::default());
    d.proxy.fault.lock().await.hold_put = Some(gate.clone());
    let key = Uuid::new_v4();
    let sending = d.clone();
    let request = tokio::spawn(async move {
        sending
            .upload("writer", "revoked.txt", b"content", key, None)
            .await
    });
    tokio::time::timeout(Duration::from_secs(10), gate.entered.notified())
        .await
        .unwrap();
    // The reservation is committed, and the remote transfer holds no SQL lock.
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/folders/{}", d.folder.id),
            Value::Null
        )
        .await
        .0,
        409
    );
    control_plane::spaces::revoke(
        &d.e.pool,
        "alice",
        d.folder.space_id,
        Role::Editor,
        "writer",
    )
    .await
    .unwrap();
    gate.release.notify_one();
    let (status, error) = request.await.unwrap();
    assert_eq!(status, 403, "{error}");
    crate::grant(&d.e, d.folder.space_id, Role::Editor, "writer").await;
    let (_, receipt) = d
        .json(
            "writer",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null,
        )
        .await;
    assert_eq!(receipt["status"], "failed");
    d.storage.cleanup_tick().await.unwrap();
    let (a, b) = tokio::join!(
        d.upload(
            "writer",
            "revoked.txt",
            b"content",
            Uuid::new_v4(),
            Some(key)
        ),
        d.upload(
            "writer",
            "revoked.txt",
            b"content",
            Uuid::new_v4(),
            Some(key)
        )
    );
    let mut statuses = vec![a.0, b.0];
    statuses.sort();
    assert_eq!(statuses, vec![201, 409], "{a:?} {b:?}");
    let (_, old) = d
        .json(
            "writer",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null,
        )
        .await;
    assert!(old["successor_key"].is_string());
    assert!(old["acknowledged_at"].is_string());
    let key = Uuid::new_v4();
    let gate = Arc::new(crate::support::Gate::default());
    d.proxy.fault.lock().await.hold_put = Some(gate.clone());
    let sending = d.clone();
    let request = tokio::spawn(async move {
        sending
            .upload("writer", "late.txt", b"late", key, None)
            .await
    });
    tokio::time::timeout(Duration::from_secs(10), gate.entered.notified())
        .await
        .unwrap();
    let object:String=sqlx::query_scalar("update document_upload set expires_at=clock_timestamp()-interval '1 second' where request_key=$1 returning object_key").bind(key).fetch_one(&d.e.pool).await.unwrap();
    d.storage.cleanup_tick().await.unwrap();
    let cleaned: bool = sqlx::query_scalar(
        "select cleaned_at is not null from document_upload where request_key=$1",
    )
    .bind(key)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert!(
        !cleaned,
        "an expired lease cannot complete a PUT still in flight"
    );
    gate.release.notify_one();
    let (status, body) = request.await.unwrap();
    assert_eq!(status, 409, "{body}");
    assert!(d.bucket.store.get(&object).await.is_ok());
    let (a, b) = tokio::join!(d.storage.cleanup_tick(), d.storage.cleanup_tick());
    a.unwrap();
    b.unwrap();
    assert!(d.bucket.store.get(&object).await.is_err());
    let (_, stats) = d
        .json(
            "writer",
            "GET",
            &format!("/spaces/{}/storage", d.folder.space_id),
            Value::Null,
        )
        .await;
    assert_eq!(stats["used_bytes"], 7);
    assert_eq!(stats["reserved_bytes"], 0);
    // Successful originals survive every inventory pass.
    let ready: String = sqlx::query_scalar("select object_key from document_current")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(d.bucket.store.get(&ready).await.is_ok());
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_lost_ack_and_unavailable_provider_keep_durable_outcomes() {
    let d = Documents::start(1024).await;
    d.proxy.fault.lock().await.lose_put_ack = true;
    let (status, receipt) = d
        .upload("writer", "ack.txt", b"content", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 503, "{receipt}");
    let (uncertain, original): (bool, String) =
        sqlx::query_as("select put_pending,object_key from document_upload where name='ack.txt'")
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert!(uncertain);
    d.storage.cleanup_tick().await.unwrap();
    assert!(
        d.bucket.store.get(&original).await.is_ok(),
        "read-back does not prove the timed-out writer ended"
    );
    d.proxy.fault.lock().await.lose_put_ack = false;
    d.proxy.fault.lock().await.deny_put = true;
    let key = Uuid::new_v4();
    let (status, error) = d
        .upload("writer", "unavailable.txt", b"content", key, None)
        .await;
    assert_eq!(status, 503, "{error}");
    let (_, receipt) = d
        .json(
            "writer",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null,
        )
        .await;
    assert_eq!(receipt["status"], "failed");
    d.proxy.fault.lock().await.deny_put = false;
    assert_eq!(
        d.upload("writer", "unavailable.txt", b"content", key, None)
            .await
            .0,
        409
    );
    assert_eq!(
        d.upload(
            "writer",
            "unavailable.txt",
            b"different",
            Uuid::new_v4(),
            Some(key)
        )
        .await
        .0,
        409
    );
    sqlx::query("update document_storage set orphan_bytes=$1")
        .bind(d.storage.config.limits.cleanup_backlog_bytes)
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(
        d.upload("writer", "backlog.txt", b"content", Uuid::new_v4(), None)
            .await
            .0,
        503
    );
    sqlx::query("update document_storage set orphan_bytes=0")
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(
        d.upload(
            "writer",
            "unavailable.txt",
            b"content",
            Uuid::new_v4(),
            Some(key)
        )
        .await
        .0,
        201
    );
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_slow_consumer_cannot_hold_download_capacity() {
    let d = Documents::start(1024 * 1024).await;
    let (status, receipt) = d
        .upload(
            "writer",
            "stream.txt",
            &vec![1; 512 * 1024],
            Uuid::new_v4(),
            None,
        )
        .await;
    assert_eq!(status, 201, "{receipt}");
    let path = format!(
        "/documents/{}/content",
        receipt["document_id"].as_str().unwrap()
    );
    let first = d
        .request("reader", "GET", &path, Body::empty(), "", None)
        .await;
    assert_eq!(first.status(), 200);
    // Keep the response alive without polling its body: exercise downstream backpressure.
    assert_eq!(
        d.request("reader", "GET", &path, Body::empty(), "", None)
            .await
            .status(),
        429
    );
    tokio::time::sleep(Duration::from_millis(2200)).await;
    let next = d
        .request("reader", "GET", &path, Body::empty(), "", None)
        .await;
    assert_eq!(next.status(), 200);
    assert_eq!(
        to_bytes(next.into_body(), 1024 * 1024).await.unwrap().len(),
        512 * 1024
    );
    assert!(
        to_bytes(first.into_body(), 1024 * 1024)
            .await
            .unwrap()
            .len()
            < 512 * 1024
    );
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn document_cleanup_skips_a_contended_organization_without_starving_other_work() {
    let d = Documents::start(1024).await;
    assert_eq!(
        d.upload("writer", "ready.txt", b"ready", Uuid::new_v4(), None)
            .await
            .0,
        201
    );
    let peer = crate::support::member_organization(&d.e.pool, "Peer", "peer-owner")
        .await
        .unwrap();
    let id = Uuid::new_v4();
    let failed = Uuid::new_v4();
    let pending_key:String=sqlx::query_scalar("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,reserved_bytes) select $1,$1,actor,organization_id,space_id,folder_id,quota_owner,'pending.txt',mime,size,sha256,replace(object_key,id::text,$1::text),'pending',clock_timestamp()-interval '1 second',size from document_upload where status='stored' returning object_key")
        .bind(id).fetch_one(&d.e.pool).await.unwrap();
    let failed_key:String=sqlx::query_scalar("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,completed_at) select $1,$1,'peer-owner',$2,$2,folder_id,$2,'failed.txt',mime,size,sha256,replace(object_key,id::text,$1::text),'failed',clock_timestamp()-interval '1 second',clock_timestamp() from document_upload where status='stored' returning object_key")
        .bind(failed).bind(peer.id).fetch_one(&d.e.pool).await.unwrap();
    let installation: Uuid = sqlx::query_scalar("select namespace from document_storage")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    for key in [&pending_key, &failed_key] {
        d.bucket
            .client
            .put_object()
            .bucket("originals")
            .key(key)
            .metadata("fred-installation", installation.to_string())
            .body(ByteStream::from_static(b"orphan"))
            .send()
            .await
            .unwrap();
    }
    let org: Uuid = sqlx::query_scalar("select organization_id from document_upload where id=$1")
        .bind(id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let held = crate::hold_organization_lock(&d.e, org).await;
    d.storage.cleanup_tick().await.unwrap();
    assert!(d.bucket.store.get(&failed_key).await.is_err());
    assert!(d.bucket.store.get(&pending_key).await.is_ok());
    let status: String = sqlx::query_scalar("select status from document_upload where id=$1")
        .bind(id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(status, "pending");
    held.rollback().await.unwrap();
    sqlx::query("update document_upload set cleanup_due_at=clock_timestamp() where id=$1")
        .bind(id)
        .execute(&d.e.pool)
        .await
        .unwrap();
    d.storage.cleanup_tick().await.unwrap();
    assert!(d.bucket.store.get(&pending_key).await.is_err());
}

#[path = "document_processing.rs"]
mod processing;

// Proves: I22, I25
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn shared_swift_bucket_cleanup_preserves_foreign_objects_and_reclaims_owned_late_writes() {
    let d = Documents::start(1024).await;
    sqlx::raw_sql("create table cleanup_renewal_probe(n int); create function count_cleanup_renewals() returns trigger language plpgsql as $$ begin if new.lease_until is not null then insert into cleanup_renewal_probe values(1); end if; return new; end $$; create trigger cleanup_renewal_probe after update of lease_until on document_storage for each row execute function count_cleanup_renewals()")
        .execute(&d.e.pool).await.unwrap();
    let (status, receipt) = d
        .upload("writer", "source.txt", b"source", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{receipt}");
    let (document, original): (Uuid, String) =
        sqlx::query_as("select id,object_key from document_current")
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(original, format!("{document}/input/source.txt"));
    let installation: Uuid = sqlx::query_scalar("select namespace from document_storage")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let foreign = Uuid::new_v4();
    let sentinels = [
        (format!("{foreign}/input/swift.txt"), None),
        (
            format!("{foreign}/input/another-installation.txt"),
            Some(Uuid::new_v4().to_string()),
        ),
        (
            format!("{document}/output/processing/generation/output.md"),
            Some(installation.to_string()),
        ),
        ("legacy-document/output/native.pdf".into(), None),
    ];
    for (key, owner) in &sentinels {
        let mut put = d
            .bucket
            .client
            .put_object()
            .bucket("originals")
            .key(key)
            .body(ByteStream::from_static(b"preserved"));
        if let Some(owner) = owner {
            put = put.metadata("fred-installation", owner);
        }
        put.send().await.unwrap();
    }
    let late = format!("{}/input/expired.txt", Uuid::new_v4());
    // The receipt has expired: the durable object marker still proves installation ownership.
    for _ in 0..2 {
        d.bucket
            .client
            .put_object()
            .bucket("originals")
            .key(&late)
            .metadata("fred-installation", installation.to_string())
            .body(ByteStream::from_static(b"late"))
            .send()
            .await
            .unwrap();
        d.storage.cleanup_tick().await.unwrap();
        // Claim, pre-list, four input candidates and final renewal. Output keys
        // must not cause a SQL lease update in a shared documents bucket.
        let renewals: i64 = sqlx::query_scalar("select count(*) from cleanup_renewal_probe")
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
        assert_eq!(renewals, 7);
        sqlx::query("delete from cleanup_renewal_probe")
            .execute(&d.e.pool)
            .await
            .unwrap();
        assert!(d.bucket.store.get(&late).await.is_err());
        assert!(d.bucket.store.get(&original).await.is_ok());
        for (key, _) in &sentinels {
            assert!(
                d.bucket.store.get(key).await.is_ok(),
                "removed foreign key {key}"
            );
        }
    }
}

// Proves: I22, I25
#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn cleanup_inaccessible_original_does_not_starve_other_objects() {
    let d = Documents::start(1024).await;
    assert_eq!(
        d.upload("writer", "source.txt", b"source", Uuid::new_v4(), None)
            .await
            .0,
        201
    );
    let installation: Uuid = sqlx::query_scalar("select namespace from document_storage")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let mut failed = Vec::new();
    for age in [2, 1] {
        let id = Uuid::new_v4();
        let key: String = sqlx::query_scalar("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,completed_at,cleanup_due_at) select $1,$1,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,replace(object_key,id::text,$1::text),'failed',clock_timestamp()-interval '1 second',clock_timestamp(),clock_timestamp()-make_interval(secs=>$2) from document_upload where status='stored' returning object_key")
            .bind(id).bind(age as f64).fetch_one(&d.e.pool).await.unwrap();
        d.bucket
            .client
            .put_object()
            .bucket("originals")
            .key(&key)
            .metadata("fred-installation", installation.to_string())
            .body(ByteStream::from_static(b"orphan"))
            .send()
            .await
            .unwrap();
        failed.push((id, key));
    }
    d.proxy.fault.lock().await.deny_head_path = Some(format!("/originals/{}", failed[0].1));
    d.storage.cleanup_tick().await.unwrap();
    assert!(d.bucket.store.get(&failed[0].1).await.is_ok());
    assert!(d.bucket.store.get(&failed[1].1).await.is_err());
    let deferred: bool = sqlx::query_scalar("select cleaned_at is null and cleanup_attempts=1 and cleanup_due_at>clock_timestamp() from document_upload where id=$1")
        .bind(failed[0].0).fetch_one(&d.e.pool).await.unwrap();
    assert!(deferred);
    let scanned: bool = sqlx::query_scalar(
        "select inventory_completed_at is not null and orphan_bytes>0 from document_storage",
    )
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert!(scanned);
    d.proxy.fault.lock().await.deny_head_path = None;
    d.storage.cleanup_tick().await.unwrap();
    assert!(d.bucket.store.get(&failed[0].1).await.is_err());
}

// The same real S3 fixture and fault proxy as document uploads exercise CP-owned
// PowerPoint originals; byte validation belongs to the capability, not this API.
impl Documents {
    async fn stage_ppt(&self, user: &str, path: &str, bytes: &[u8], key: Uuid) -> (u16, Value) {
        let mut body = b"--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"template.pptx\"\r\nContent-Type: application/octet-stream\r\n\r\n".to_vec();
        body.extend_from_slice(bytes);
        body.extend_from_slice(b"\r\n--fixture--\r\n");
        json_response(
            self.request(
                user,
                "PUT",
                path,
                Body::from(body),
                "multipart/form-data; boundary=fixture",
                Some(key),
            )
            .await,
        )
        .await
    }
    async fn ppt_agent(&self) -> Uuid {
        let id = Uuid::new_v4();
        let org: Uuid = sqlx::query_scalar("select organization_id from space where id=$1")
            .bind(self.folder.space_id)
            .fetch_one(&self.e.pool)
            .await
            .unwrap();
        sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$3,'fixture','assistant',$1::text,'{\"role\":\"Assistant\",\"usage_statement\":\"Test\",\"selected_capability_ids\":[\"ppt_builder\"],\"capability_config\":{\"ppt_builder\":{\"schema_version\":\"1\",\"config\":{\"use_vision\":false}}}}','writer',$1::text)")
            .bind(id).bind(self.folder.space_id).bind(control_plane::agents::template_id(org,"fixture","assistant")).execute(&self.e.pool).await.unwrap();
        sqlx::query("insert into agent_template_policy(organization_id,template_id) values($1,$2) on conflict do nothing")
            .bind(org)
            .bind(control_plane::agents::template_id(org,"fixture","assistant"))
            .execute(&self.e.pool)
            .await
            .unwrap();
        id
    }
    async fn ppt_sweep(&self) {
        // Advance only the fixture's cleanup clock; immutable upload expiry stays intact.
        sqlx::query("update powerpoint_file set cleanup_due_at=clock_timestamp()-interval '1 second' where status='retired'").execute(&self.e.pool).await.unwrap();
        self.storage.cleanup_tick().await.unwrap();
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres and SeaweedFS"]
async fn powerpoint_ownership_fallback_replacement_and_cleanup() {
    let d = Documents::start(100_000).await;
    let space = d.folder.space_id;
    let org: Uuid = sqlx::query_scalar("select organization_id from space where id=$1")
        .bind(space)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    crate::grant(&d.e, org, Role::Owner, "org-owner").await;
    let agent = d.ppt_agent().await;
    let other_agent = d.ppt_agent().await;
    let path = format!("/spaces/{space}/powerpoint-template?agent_instance_id={agent}");
    let org_path = format!("/spaces/{org}/powerpoint-template?runtime_id=fixture");
    assert_eq!(d.ppt("reader", &path, b"a", Uuid::new_v4()).await.0, 403);
    assert_eq!(
        d.ppt("writer", &org_path, b"a", Uuid::new_v4()).await.0,
        403
    );
    assert_eq!(
        d.ppt(
            "owner",
            &format!("/spaces/{space}/powerpoint-template?runtime_id=fixture"),
            b"a",
            Uuid::new_v4()
        )
        .await
        .0,
        404
    );
    let (status, organization) = d
        .ppt("org-owner", &org_path, b"organization", Uuid::new_v4())
        .await;
    assert_eq!(status, 200, "{organization}");
    // A direct role on the usage space suffices; the file does not grant an org read role.
    sqlx::query("delete from space_role_grant where space_id=$1 and subject='reader'")
        .bind(org)
        .execute(&d.e.pool)
        .await
        .unwrap();
    let (status, resolution) = d.json("reader", "GET", &path, json!({})).await;
    assert_eq!(status, 200, "{resolution}");
    assert_eq!(resolution["source"], "organization");
    assert_eq!(resolution["file"]["id"], organization["id"]);
    assert_eq!(resolution["activation_ready"], true);
    let key = Uuid::new_v4();
    let (status, own) = d.ppt("writer", &path, b"own", key).await;
    assert_eq!(status, 200, "{own}");
    assert_eq!(d.ppt("writer", &path, b"own", key).await.1["id"], own["id"]);
    assert_eq!(d.ppt("writer", &path, b"different", key).await.0, 409);
    let own_id = own["id"].as_str().unwrap();
    let content =
        format!("/spaces/{space}/powerpoint-template/{own_id}/content?agent_instance_id={agent}");
    let response = d
        .request("reader", "GET", &content, Body::empty(), "", None)
        .await;
    assert_eq!(response.status(), 200);
    assert_eq!(to_bytes(response.into_body(), 100).await.unwrap(), "own");
    let wrong = format!(
        "/spaces/{space}/powerpoint-template/{own_id}/content?agent_instance_id={other_agent}"
    );
    assert_eq!(
        d.request("reader", "GET", &wrong, Body::empty(), "", None)
            .await
            .status(),
        404
    );
    assert_eq!(d.ppt("writer", &path, b"new", Uuid::new_v4()).await.0, 409);
    let replace = format!("{path}&expected_file_id={own_id}");
    let (a, b) = tokio::join!(
        d.ppt("writer", &replace, b"first", Uuid::new_v4()),
        d.ppt("writer", &replace, b"second", Uuid::new_v4())
    );
    assert!(
        (a.0 == 200 && b.0 == 409) || (b.0 == 200 && a.0 == 409),
        "{a:?} {b:?}"
    );
    let winner = if a.0 == 200 { a.1 } else { b.1 };
    let remove = format!("{path}&expected_file_id={}", winner["id"].as_str().unwrap());
    assert_eq!(
        d.request("writer", "DELETE", &remove, Body::empty(), "", None)
            .await
            .status(),
        202
    );
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["source"],
        "organization"
    );
    d.ppt_sweep().await;
    let receipt = d
        .json(
            "writer",
            "GET",
            &format!("/powerpoint-uploads/{key}"),
            json!({}),
        )
        .await
        .1;
    assert_eq!(receipt["status"], "retired");
    assert!(receipt["cleaned_at"].is_string());
    // Logical ownership is independent of the depositor; cleanup survives agent deletion.
    let (status, last) = d.ppt("writer", &path, b"last", Uuid::new_v4()).await;
    assert_eq!(status, 200, "{last}");
    let deleted = d
        .request(
            "writer",
            "DELETE",
            &format!("/spaces/{space}/agent-instances/{agent}"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(deleted.status(), 202);
    d.ppt_sweep().await;
    let live: (Option<Uuid>, Option<chrono::DateTime<chrono::Utc>>) =
        sqlx::query_as("select live_agent_id,cleaned_at from powerpoint_file where id=$1")
            .bind(Uuid::parse_str(last["id"].as_str().unwrap()).unwrap())
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert!(live.0.is_none() && live.1.is_some());
}

#[tokio::test]
#[ignore = "needs disposable Postgres and SeaweedFS"]
async fn powerpoint_interruption_replay_and_cleanup_retry() {
    let d = Arc::new(Documents::start(100_000).await);
    let agent = d.ppt_agent().await;
    let space = d.folder.space_id;
    let path = format!("/spaces/{space}/powerpoint-template?agent_instance_id={agent}");
    let (_, original) = d.ppt("writer", &path, b"original", Uuid::new_v4()).await;
    let replace = format!(
        "{path}&expected_file_id={}",
        original["id"].as_str().unwrap()
    );
    let key = Uuid::new_v4();
    let gate = Arc::new(crate::support::Gate::default());
    d.proxy.fault.lock().await.hold_put = Some(gate.clone());
    let sending = {
        let d = d.clone();
        let replace = replace.clone();
        tokio::spawn(async move { d.ppt("writer", &replace, b"replacement", key).await })
    };
    tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
        .await
        .unwrap();
    let org = control_plane::spaces::load(&d.e.pool, space)
        .await
        .unwrap()
        .organization;
    let lock = tokio::time::timeout(
        Duration::from_secs(1),
        crate::hold_organization_lock(&d.e, org),
    )
    .await
    .expect("PowerPoint transfer retained a SQL lock");
    lock.rollback().await.unwrap();
    // Crash after durable reservation and before receiving S3's answer.
    sending.abort();
    assert!(sending.await.unwrap_err().is_cancelled());
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["file"]["id"],
        original["id"]
    );
    gate.release.notify_one();
    let (status, resumed) = d.ppt("writer", &replace, b"replacement", key).await;
    assert_eq!(status, 200, "{resumed}");
    let count: i64 =
        sqlx::query_scalar("select count(*) from powerpoint_file where request_key=$1")
            .bind(key)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(count, 1);
    let object_key: String =
        sqlx::query_scalar("select object_key from powerpoint_file where id=$1")
            .bind(Uuid::parse_str(original["id"].as_str().unwrap()).unwrap())
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    d.proxy.fault.lock().await.deny_head_path = Some(format!("/originals/{object_key}"));
    d.ppt_sweep().await;
    let (cleaned, error): (Option<chrono::DateTime<chrono::Utc>>, Option<String>) =
        sqlx::query_as("select cleaned_at,error_code from powerpoint_file where object_key=$1")
            .bind(&object_key)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert!(cleaned.is_none());
    assert_eq!(error.as_deref(), Some("cleanup_failed"));
    assert!(d.bucket.store.get(&object_key).await.is_ok());
    d.proxy.fault.lock().await.deny_head_path = None;
    d.ppt_sweep().await;
    assert!(d.bucket.store.get(&object_key).await.is_err());
    let attempts: i32 =
        sqlx::query_scalar("select cleanup_attempts from powerpoint_file where object_key=$1")
            .bind(&object_key)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(attempts, 2);
    // A rejected network write keeps the last saved attachment and is replayable.
    d.proxy.fault.lock().await.deny_put = true;
    let next = format!(
        "{path}&expected_file_id={}",
        resumed["id"].as_str().unwrap()
    );
    let next_key = Uuid::new_v4();
    assert_eq!(d.ppt("writer", &next, b"third", next_key).await.0, 503);
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["file"]["id"],
        resumed["id"]
    );
    d.proxy.fault.lock().await.deny_put = false;
    assert_eq!(d.ppt("writer", &next, b"third", next_key).await.0, 200);
    // A process that never returns leaves a durable reservation and immutable key.
    let abandoned = Uuid::new_v4();
    let abandoned_key: String = sqlx::query_scalar("insert into powerpoint_file(id,request_key,actor,organization_id,space_id,agent_instance_id,live_space_id,live_agent_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,cleanup_due_at) select $1,$1,actor,organization_id,space_id,agent_instance_id,live_space_id,live_agent_id,quota_owner,name,mime,size,sha256,replace(object_key,id::text,$1::text),'pending',clock_timestamp()-interval '1 second',clock_timestamp()-interval '1 second' from powerpoint_file where request_key=$2 returning object_key")
        .bind(abandoned).bind(next_key).fetch_one(&d.e.pool).await.unwrap();
    let file = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(file.path(), b"third").unwrap();
    let hash: [u8; 32] = Sha256::digest(b"third").into();
    d.storage
        .objects
        .put_verified(&abandoned_key, file.path(), 5, &hash)
        .await
        .unwrap();
    d.storage.cleanup_tick().await.unwrap();
    let abandoned_receipt = d
        .json(
            "writer",
            "GET",
            &format!("/powerpoint-uploads/{abandoned}"),
            json!({}),
        )
        .await
        .1;
    assert_eq!(abandoned_receipt["status"], "retired");
    assert!(abandoned_receipt["cleaned_at"].is_string());
    assert!(d.bucket.store.get(&abandoned_key).await.is_err());
}

#[tokio::test]
#[ignore = "needs disposable Postgres and SeaweedFS"]
async fn powerpoint_space_deletion_waits_for_original_and_derived_cleanup() {
    use control_plane::lifecycle::{Lifecycle, Status, cleanup, store};
    let d = Documents::start(100_000).await;
    let agent = d.ppt_agent().await;
    let space = d.folder.space_id;
    let org = control_plane::spaces::load(&d.e.pool, space)
        .await
        .unwrap()
        .organization;
    crate::grant(&d.e, org, Role::Owner, "org-owner").await;
    assert_eq!(
        d.ppt(
            "org-owner",
            &format!("/spaces/{org}/powerpoint-template?runtime_id=fixture"),
            b"org",
            Uuid::new_v4()
        )
        .await
        .0,
        200
    );
    assert_eq!(
        d.ppt(
            "writer",
            &format!("/spaces/{space}/powerpoint-template?agent_instance_id={agent}"),
            b"agent",
            Uuid::new_v4()
        )
        .await
        .0,
        200
    );
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    let receipt = lifecycle
        .accept(&d.e.pool, "fixture-root", org, false)
        .await
        .unwrap();
    for _ in 0..4 {
        cleanup::batch(&d.e.pool, receipt.id, &Default::default(), Some(&d.storage))
            .await
            .unwrap();
    }
    assert_ne!(
        store::status(&d.e.pool, "fixture-root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    for _ in 0..10 {
        d.ppt_sweep().await;
        let (_, obsolete) = d
            .worker(
                "GET",
                "/cleanup?runtime_id=fixture",
                json!(null),
                "preparation-worker",
            )
            .await;
        for preparation in obsolete.as_array().unwrap() {
            assert_eq!(
                d.worker(
                    "POST",
                    &format!("/{}/cleaned", preparation.as_str().unwrap()),
                    json!(null),
                    "preparation-worker"
                )
                .await
                .0,
                204
            );
        }
        cleanup::batch(&d.e.pool, receipt.id, &Default::default(), Some(&d.storage))
            .await
            .unwrap();
        if store::status(&d.e.pool, "fixture-root", receipt.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
    }
    assert_eq!(
        store::status(&d.e.pool, "fixture-root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    let pending: i64 = sqlx::query_scalar("select count(*) from powerpoint_file where cleaned_at is null or live_space_id is not null or live_agent_id is not null").fetch_one(&d.e.pool).await.unwrap();
    assert_eq!(pending, 0);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from powerpoint_file")
            .fetch_one(&d.e.pool)
            .await
            .unwrap(),
        2
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres"]
async fn powerpoint_sql_ownership_constraints() {
    let pool = crate::environment::database::database().await;
    let org = crate::support::member_organization(&pool, "Existing organization", "alice")
        .await
        .unwrap();
    // Raw schema inserts require the budgets normally initialized by storage admission.
    sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'local',100000,0,0),($1,'organization_total',100000,0,0)")
        .bind(org.id).execute(&pool).await.unwrap();
    let agent = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'fixture','assistant','Existing agent','{}','alice',$1::text)").bind(agent).bind(org.id).execute(&pool).await.unwrap();
    assert!(
        control_plane::agent_instances::get_for_space(&pool, org.id, agent)
            .await
            .unwrap()
            .is_some()
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from powerpoint_file")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
    let insert = "insert into powerpoint_file(id,request_key,actor,organization_id,space_id,agent_instance_id,live_space_id,live_agent_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,cleanup_due_at) values($1,$1,'alice',$2,$3,$4,$3,$4,$3,'template.pptx','application/octet-stream',3,repeat('a',64),$1::text,'pending',clock_timestamp()+interval '5 minutes',clock_timestamp())";
    let id = Uuid::new_v4();
    sqlx::query(insert)
        .bind(id)
        .bind(org.id)
        .bind(org.id)
        .bind(agent)
        .execute(&pool)
        .await
        .unwrap();
    // Neither a foreign organization nor a guessed agent can become the owner.
    for (organization, instance) in [(Uuid::new_v4(), agent), (org.id, Uuid::new_v4())] {
        assert!(
            sqlx::query(insert)
                .bind(Uuid::new_v4())
                .bind(organization)
                .bind(org.id)
                .bind(instance)
                .execute(&pool)
                .await
                .is_err()
        );
    }
    sqlx::query(
        "update powerpoint_file set status='stored',published_at=clock_timestamp() where id=$1",
    )
    .bind(id)
    .execute(&pool)
    .await
    .unwrap();
    let second = Uuid::new_v4();
    sqlx::query(insert)
        .bind(second)
        .bind(org.id)
        .bind(org.id)
        .bind(agent)
        .execute(&pool)
        .await
        .unwrap();
    let error = sqlx::query(
        "update powerpoint_file set status='stored',published_at=clock_timestamp() where id=$1",
    )
    .bind(second)
    .execute(&pool)
    .await
    .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23505")
    );
    assert!(
        sqlx::query("update powerpoint_file set agent_instance_id=$2 where id=$1")
            .bind(id)
            .bind(Uuid::new_v4())
            .execute(&pool)
            .await
            .is_err()
    );
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(agent)
        .execute(&pool)
        .await
        .unwrap();
    let (historical, live, status): (Uuid, Option<Uuid>, String) = sqlx::query_as(
        "select agent_instance_id,live_agent_id,status from powerpoint_file where id=$1",
    )
    .bind(id)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(historical, agent);
    assert!(live.is_none());
    assert_eq!(status, "retired");
    assert!(
        sqlx::query("update powerpoint_file set status='pending' where id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .is_err()
    );
}

impl Documents {
    async fn save_ppt(&self, agent: Uuid, file: Uuid, expected: Option<Uuid>) -> (u16, Value) {
        self.json(
            "writer",
            "PATCH",
            &format!("/spaces/{}/agent-instances/{agent}", self.folder.space_id),
            json!({"powerpoint":{"file_id":file,"expected_file_id":expected}}),
        )
        .await
    }
    async fn preparation(&self, file: &Value) -> Uuid {
        sqlx::query_scalar("select id from capability_preparation where file_id=$1 and state<>'obsolete' order by created_at desc limit 1").bind(file["id"].as_str().unwrap().parse::<Uuid>().unwrap()).fetch_one(&self.e.pool).await.unwrap()
    }
    async fn worker(&self, method: &str, path: &str, body: Value, client: &str) -> (u16, Value) {
        let now = chrono::Utc::now().timestamp();
        let token=self.identity.sign(json!({"sub":"worker","preferred_username":format!("service-account-{client}"),"iss":self.identity.realm,"aud":"app","azp":client,"client_id":client,"iat":now,"exp":now+600}));
        json_response(
            self.app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(method)
                        .uri(format!("/v1/capability-preparations{path}"))
                        .header("authorization", format!("Bearer {token}"))
                        .header("content-type", "application/json")
                        .body(Body::from(body.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap(),
        )
        .await
    }
    async fn confirm_ppt(&self, id: Uuid, error: Option<&str>) -> (u16, Value) {
        self.worker("POST",&format!("/{id}/confirm"),json!({"reference":if error.is_none(){Some(format!("prep:{id}"))}else{None},"error":error}),"preparation-worker").await
    }
    // Persistence regressions use the full stage -> save -> authenticated callback
    // journey; tests below stop between these boundaries to exercise interruption.
    async fn ppt(&self, user: &str, path: &str, bytes: &[u8], key: Uuid) -> (u16, Value) {
        let (status, file) = self.stage_ppt(user, path, bytes, key).await;
        if status != 200 {
            return (status, file);
        }
        let url = reqwest::Url::parse(&format!("http://fixture{path}")).unwrap();
        let query: std::collections::HashMap<_, _> = url.query_pairs().collect();
        if let Some(agent) = query.get("agent_instance_id")
            && file["status"] != "stored"
        {
            let saved = self
                .save_ppt(
                    agent.parse().unwrap(),
                    file["id"].as_str().unwrap().parse().unwrap(),
                    query.get("expected_file_id").map(|id| id.parse().unwrap()),
                )
                .await;
            if saved.0 != 200 {
                return saved;
            }
        }
        let id = self.preparation(&file).await;
        let confirmation = self.confirm_ppt(id, None).await;
        assert_eq!(confirmation.0, 204, "{confirmation:?}");
        (status, file)
    }
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn powerpoint_durable_preparation_acceptance_and_fencing() {
    let d = Documents::start(100_000).await;
    let agent = d.ppt_agent().await;
    let space = d.folder.space_id;
    let agent_path = format!("/spaces/{space}/agent-instances/{agent}");
    let path = format!("/spaces/{space}/powerpoint-template?agent_instance_id={agent}");
    let (_, file) = d.stage_ppt("writer", &path, b"model", Uuid::new_v4()).await;
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["source"],
        "builtin"
    );
    let id = file["id"].as_str().unwrap().parse().unwrap();
    let saved = d.save_ppt(agent, id, None).await;
    assert_eq!(saved.0, 200, "{saved:?}");
    assert_eq!(saved.1["preparation_state"], "pending");
    let prep = d.preparation(&file).await;
    let renamed = d
        .json(
            "writer",
            "PATCH",
            &agent_path,
            json!({"display_name":"Renamed while pending"}),
        )
        .await;
    assert_eq!(renamed.0, 200, "{renamed:?}");
    assert_eq!(renamed.1["preparation_state"], "pending");
    assert!(
        renamed.1["configuration_revision"].as_i64().unwrap()
            > saved.1["configuration_revision"].as_i64().unwrap()
    );
    assert_eq!(d.preparation(&file).await, prep);
    let admission = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{space}/agent-instances/{agent}/runtime"),
            json!({}),
        )
        .await;
    assert_eq!(admission.0, 409, "{admission:?}");
    assert_eq!(admission.1["code"], "agent_capability_pending");
    assert_eq!(
        d.worker("GET", &format!("/{prep}"), json!(null), "wrong-pod")
            .await
            .0,
        403
    );
    assert_eq!(
        d.worker(
            "GET",
            &format!("/{prep}"),
            json!(null),
            "preparation-worker"
        )
        .await
        .0,
        200
    );
    assert_eq!(d.confirm_ppt(prep, None).await.0, 204);
    assert_eq!(d.confirm_ppt(prep, None).await.0, 204);
    let edited = d
        .json("writer", "PATCH", &agent_path, json!({"display_name":"Renamed while ready", "description":"A useful presentation agent", "role":"Presentation specialist"}))
        .await;
    assert_eq!(edited.0, 200, "{edited:?}");
    assert_eq!(edited.1["preparation_state"], "ready");
    assert!(
        edited.1["configuration_revision"].as_i64().unwrap()
            > renamed.1["configuration_revision"].as_i64().unwrap()
    );
    assert_eq!(d.preparation(&file).await, prep);
    let unchanged = d.json("writer", "PATCH", &agent_path, json!({})).await;
    assert_eq!(unchanged.0, 200, "{unchanged:?}");
    assert_eq!(unchanged.1["preparation_state"], "ready");
    assert_eq!(
        unchanged.1["configuration_revision"],
        edited.1["configuration_revision"]
    );
    assert_eq!(d.preparation(&file).await, prep);
    // The accepted result remains injectable after the admission revision changes.
    let admitted = d
        .json("reader", "GET", &format!("{agent_path}/runtime"), json!({}))
        .await;
    assert_eq!(admitted.0, 200, "{admitted:?}");
    assert_eq!(
        admitted.1["agent"]["configuration"]["capability_config"]["ppt_builder"]["config"]["analysis_id"],
        format!("prep:{prep}")
    );
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["activation_ready"],
        true
    );
    let replace = format!("{path}&expected_file_id={id}");
    let (_, bad) = d
        .stage_ppt("writer", &replace, b"reject", Uuid::new_v4())
        .await;
    let refused = d
        .save_ppt(
            agent,
            bad["id"].as_str().unwrap().parse().unwrap(),
            Some(id),
        )
        .await;
    assert_eq!(refused.0, 422, "{refused:?}");
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["file"]["id"],
        file["id"]
    );
    let (_, next) = d
        .stage_ppt("writer", &replace, b"replacement", Uuid::new_v4())
        .await;
    assert_eq!(
        d.save_ppt(
            agent,
            next["id"].as_str().unwrap().parse().unwrap(),
            Some(id)
        )
        .await
        .0,
        200
    );
    let second = d.preparation(&next).await;
    assert_ne!(second, prep);
    assert_eq!(d.confirm_ppt(prep, None).await.0, 204); // obsolete acknowledgement cannot validate the replacement
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["preparation_state"],
        "pending"
    );
    assert_eq!(
        d.confirm_ppt(second, Some("No usable layouts")).await.0,
        204
    );
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["preparation_state"],
        "failed"
    );
    let failed_edit = d
        .json(
            "writer",
            "PATCH",
            &agent_path,
            json!({"description":"A clearer description"}),
        )
        .await;
    assert_eq!(failed_edit.0, 200, "{failed_edit:?}");
    assert_eq!(failed_edit.1["preparation_state"], "failed");
    assert_eq!(failed_edit.1["preparation_error"], "No usable layouts");
    assert_eq!(d.preparation(&next).await, second);
    // Concurrent explicit retries serialize on the agent and keep a single job.
    let (retried, duplicate) = tokio::join!(
        d.json("writer", "PATCH", &agent_path, json!({})),
        d.json("writer", "PATCH", &agent_path, json!({}))
    );
    assert_eq!(retried.0, 200, "{retried:?}");
    assert_eq!(duplicate.0, 200, "{duplicate:?}");
    assert_eq!(retried.1["preparation_state"], "pending", "{retried:?}");
    assert_eq!(duplicate.1["preparation_state"], "pending", "{duplicate:?}");
    assert_eq!(
        retried.1["configuration_revision"],
        failed_edit.1["configuration_revision"]
    );
    let third = d.preparation(&next).await;
    assert_ne!(third, second);
    let jobs: i64 = sqlx::query_scalar(
        "select count(*) from capability_preparation where agent_instance_id=$1",
    )
    .bind(agent)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert_eq!(jobs, 3);
    assert_eq!(d.confirm_ppt(second, None).await.0, 204);
    assert_eq!(
        d.json("reader", "GET", &path, json!({})).await.1["preparation_state"],
        "pending"
    );
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/spaces/{space}/agent-instances/{agent}"),
            json!({})
        )
        .await
        .0,
        202
    );
    assert_eq!(d.confirm_ppt(third, None).await.0, 204);
    assert_eq!(
        d.worker(
            "GET",
            &format!("/{third}/content"),
            json!(null),
            "preparation-worker"
        )
        .await
        .0,
        409
    );
    let obsolete: String =
        sqlx::query_scalar("select state from capability_preparation where id=$1")
            .bind(third)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(obsolete, "obsolete");
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn powerpoint_organization_candidate_and_pod_isolation() {
    let d = Documents::start(100_000).await;
    let agent = d.ppt_agent().await;
    let space = d.folder.space_id;
    let org = control_plane::spaces::load(&d.e.pool, space)
        .await
        .unwrap()
        .organization;
    crate::grant(&d.e, org, Role::Owner, "org-owner").await;
    crate::grant(&d.e, org, Role::Editor, "org-editor").await;
    let foreign_org = crate::support::member_organization(&d.e.pool, "Foreign", "alice")
        .await
        .unwrap();
    crate::grant(&d.e, foreign_org.id, Role::Owner, "foreign-owner").await;
    let path = format!("/spaces/{org}/powerpoint-template?runtime_id=fixture");
    let own = format!("/spaces/{space}/powerpoint-template?agent_instance_id={agent}");
    let settings = format!("/spaces/{org}/powerpoint-template/settings?runtime_id=fixture");
    let prepare = format!("/spaces/{org}/powerpoint-template/prepare?runtime_id=fixture");
    for (denied, status) in [("org-editor", 403), ("foreign-owner", 404)] {
        for (method, endpoint, body) in [
            ("GET", path.as_str(), json!({})),
            ("GET", settings.as_str(), json!({})),
            ("PUT", settings.as_str(), json!({"config":{}})),
            ("POST", prepare.as_str(), json!({})),
            ("DELETE", path.as_str(), json!({})),
        ] {
            assert_eq!(
                d.json(denied, method, endpoint, body).await.0,
                status,
                "{denied}: {method} {endpoint}"
            );
        }
        assert_eq!(
            d.stage_ppt(denied, &path, b"denied", Uuid::new_v4())
                .await
                .0,
            status
        );
    }
    let project = control_plane::spaces::create_space(
        &d.e.pool,
        "owner",
        control_plane::domain::SpaceKind::Project,
        space,
        "PowerPoint project".into(),
        "writer",
    )
    .await
    .unwrap();
    for (owner, non_organization) in [("owner", space), ("writer", project.id)] {
        let target = format!("/spaces/{non_organization}/powerpoint-template?runtime_id=fixture");
        assert_eq!(d.json(owner, "GET", &target, json!({})).await.0, 404);
        assert_eq!(
            d.stage_ppt(owner, &target, b"not common", Uuid::new_v4())
                .await
                .0,
            404
        );
        assert_eq!(
            d.json(
                owner,
                "GET",
                &format!(
                    "/spaces/{non_organization}/powerpoint-template/settings?runtime_id=fixture"
                ),
                json!({})
            )
            .await
            .0,
            404
        );
    }
    let (status, first) = d
        .stage_ppt("org-owner", &path, b"first", Uuid::new_v4())
        .await;
    assert_eq!(status, 200, "{first:?}");
    assert_eq!(
        d.json("reader", "GET", &own, json!({})).await.1["source"],
        "builtin"
    );
    assert_eq!(
        d.confirm_ppt(d.preparation(&first).await, None).await.0,
        204
    );
    let first_id = first["id"].as_str().unwrap();
    assert_eq!(d.json("org-owner", "GET", &path, json!({})).await.0, 200);
    assert_eq!(
        d.json("org-owner", "GET", &settings, json!({})).await.0,
        200
    );
    assert_eq!(
        d.json(
            "org-owner",
            "PUT",
            &settings,
            json!({"expected_file_id":first_id,"config":{}})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        d.json(
            "org-owner",
            "POST",
            &prepare,
            json!({"expected_file_id":first_id})
        )
        .await
        .0,
        202
    );
    let content =
        format!("/spaces/{org}/powerpoint-template/{first_id}/content?runtime_id=fixture");
    assert_eq!(
        d.request("org-owner", "GET", &content, Body::empty(), "", None)
            .await
            .status(),
        200
    );
    for (denied, status) in [("org-editor", 403), ("foreign-owner", 404)] {
        assert_eq!(
            d.request(denied, "GET", &content, Body::empty(), "", None)
                .await
                .status(),
            status
        );
    }
    let replace = format!("{path}&expected_file_id={first_id}");
    let (_, second) = d
        .stage_ppt("org-owner", &replace, b"second", Uuid::new_v4())
        .await;
    assert_eq!(
        d.json("reader", "GET", &own, json!({})).await.1["file"]["id"],
        first["id"]
    );
    assert_eq!(
        d.confirm_ppt(d.preparation(&second).await, Some("Unusable layouts"))
            .await
            .0,
        204
    );
    assert_eq!(
        d.json("reader", "GET", &own, json!({})).await.1["file"]["id"],
        first["id"]
    );
    let (_, third) = d
        .stage_ppt(
            "org-owner",
            &format!("{path}&expected_file_id={}", second["id"].as_str().unwrap()),
            b"third",
            Uuid::new_v4(),
        )
        .await;
    assert_eq!(
        d.confirm_ppt(d.preparation(&third).await, None).await.0,
        204
    );
    assert_eq!(
        d.json("reader", "GET", &own, json!({})).await.1["file"]["id"],
        third["id"]
    );
    // Another logical pod never resolves this organization's template.
    let other = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) select $2,space_id,$3,'other-pod',source_agent_id,$2::text,tuning,created_by,$2::text from agent_instance where agent_instance_id=$1")
        .bind(agent).bind(other).bind(control_plane::agents::template_id(org,"other-pod","assistant")).execute(&d.e.pool).await.unwrap();
    sqlx::query("insert into agent_template_policy(organization_id,template_id) values($1,$2)")
        .bind(org)
        .bind(control_plane::agents::template_id(
            org,
            "other-pod",
            "assistant",
        ))
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(
        d.json(
            "reader",
            "GET",
            &format!("/spaces/{space}/powerpoint-template?agent_instance_id={other}"),
            json!({})
        )
        .await
        .1["source"],
        "builtin"
    );
    assert_eq!(
        d.json(
            "org-owner",
            "DELETE",
            &format!("{path}&expected_file_id={}", third["id"].as_str().unwrap()),
            json!({})
        )
        .await
        .0,
        202
    );
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn powerpoint_creation_commits_file_configuration_and_intention_together() {
    let d = Documents::start(100_000).await;
    d.ppt_agent().await;
    let space = d.folder.space_id;
    let org = control_plane::spaces::load(&d.e.pool, space)
        .await
        .unwrap()
        .organization;
    let template = control_plane::agents::template_id(org, "fixture", "assistant");
    let draft = Uuid::new_v4();
    let path = format!(
        "/spaces/{space}/powerpoint-template?agent_instance_id={draft}&template_id={template}"
    );
    let (status, file) = d
        .stage_ppt("writer", &path, b"new-agent", Uuid::new_v4())
        .await;
    assert_eq!(status, 200, "{file:?}");
    let mut body = json!({"template_id":template,"display_name":"Prepared assistant","usage_statement":"Test","powerpoint":{"file_id":file["id"]}});
    // Rejected user configuration leaves the draft unattached and no intention.
    body["display_name"] = json!("");
    assert_eq!(
        d.json(
            "writer",
            "POST",
            &format!("/spaces/{space}/agent-instances"),
            body.clone()
        )
        .await
        .0,
        422
    );
    let count: i64 =
        sqlx::query_scalar("select count(*) from capability_preparation where file_id=$1")
            .bind(file["id"].as_str().unwrap().parse::<Uuid>().unwrap())
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(count, 0);
    body["display_name"] = json!("Prepared assistant");
    let accepted = d
        .json(
            "writer",
            "POST",
            &format!("/spaces/{space}/agent-instances"),
            body,
        )
        .await;
    assert_eq!(accepted.0, 201, "{accepted:?}");
    assert_eq!(accepted.1["agent_instance_id"], draft.to_string());
    assert_eq!(accepted.1["preparation_state"], "pending");
    let preparation = d.preparation(&file).await;
    // The durable deadline also settles work whose worker never appeared.
    sqlx::query("update capability_preparation set deadline_at=clock_timestamp()-interval '1 second' where id=$1").bind(preparation).execute(&d.e.pool).await.unwrap();
    let task = tokio::spawn(control_plane::capability_preparation::dispatch::run(
        d.e.pool.clone(),
        Default::default(),
    ));
    for _ in 0..50 {
        let state: String = sqlx::query_scalar(
            "select preparation_state from agent_instance where agent_instance_id=$1",
        )
        .bind(draft)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
        if state == "failed" {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }
    task.abort();
    let _ = task.await;
    let state: String = sqlx::query_scalar(
        "select preparation_state from agent_instance where agent_instance_id=$1",
    )
    .bind(draft)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert_eq!(state, "failed");
    assert_eq!(d.confirm_ppt(preparation, None).await.0, 409);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "needs disposable PostgreSQL, SeaweedFS and Temporal"]
async fn powerpoint_dispatch_replays_one_workflow_and_reconciles_disappeared_worker() {
    use control_plane::capability_preparation::dispatch;
    use temporalio_client::{grpc::WorkflowService, tonic::Request as GrpcRequest};
    use temporalio_common::protos::temporal::api::{
        common::v1::WorkflowExecution, workflowservice::v1::TerminateWorkflowExecutionRequest,
    };
    let d = Documents::start(100_000).await;
    let agent = d.ppt_agent().await;
    let path = format!(
        "/spaces/{}/powerpoint-template?agent_instance_id={agent}",
        d.folder.space_id
    );
    let (_, file) = d
        .stage_ppt("writer", &path, b"dispatch", Uuid::new_v4())
        .await;
    assert_eq!(
        d.save_ppt(agent, file["id"].as_str().unwrap().parse().unwrap(), None)
            .await
            .0,
        200
    );
    let id = d.preparation(&file).await;
    let (_temporal, host) = processing::start_temporal();
    let mut client = processing::ready_temporal(&host).await;
    let config = control_plane::lifecycle::policy::TemporalConfig {
        host,
        ..Default::default()
    };
    dispatch::tick(&d.e.pool, &config, &client).await.unwrap();
    let first: (String, String, String) = sqlx::query_as(
        "select workflow_id,run_id,task_queue from capability_preparation where id=$1",
    )
    .bind(id)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert!(first.2.ends_with("-fixture"));
    let (_, binding) = d
        .worker(
            "GET",
            "/worker?runtime_id=fixture",
            json!(null),
            "preparation-worker",
        )
        .await;
    assert_eq!(binding["task_queue"], first.2);
    // Simulate an uncertain delivery after Temporal accepted, before SQL recorded it.
    sqlx::query("update capability_preparation set run_id=null,delivered_at=null,dispatch_until=null,delivery_due_at=clock_timestamp() where id=$1").bind(id).execute(&d.e.pool).await.unwrap();
    dispatch::tick(&d.e.pool, &config, &client).await.unwrap();
    let replay: String =
        sqlx::query_scalar("select run_id from capability_preparation where id=$1")
            .bind(id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(replay, first.1);
    client
        .terminate_workflow_execution(GrpcRequest::new(TerminateWorkflowExecutionRequest {
            namespace: "default".into(),
            workflow_execution: Some(WorkflowExecution {
                workflow_id: first.0,
                run_id: first.1,
            }),
            reason: "Disposable test: worker vanished".into(),
            ..Default::default()
        }))
        .await
        .unwrap();
    sqlx::query("update capability_preparation set delivery_due_at=clock_timestamp() where id=$1")
        .bind(id)
        .execute(&d.e.pool)
        .await
        .unwrap();
    dispatch::tick(&d.e.pool, &config, &client).await.unwrap();
    let state: (String, Option<String>) = sqlx::query_as(
        "select preparation_state,preparation_error from agent_instance where agent_instance_id=$1",
    )
    .bind(agent)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert_eq!(state.0, "failed");
    assert!(state.1.unwrap().contains("Retry or replace"));
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL and SeaweedFS"]
async fn marketplace_agent_originals_are_copied_and_prepared_independently() {
    let d = Documents::start(100_000).await;
    let source = d.ppt_agent().await;
    let space = d.folder.space_id;
    let org = control_plane::spaces::load(&d.e.pool, space)
        .await
        .unwrap()
        .organization;
    crate::grant(&d.e, org, Role::Editor, "moderator").await;
    let path = format!("/spaces/{space}/powerpoint-template?agent_instance_id={source}");
    let (status, original) = d
        .ppt(
            "writer",
            &path,
            b"frozen configuration original",
            Uuid::new_v4(),
        )
        .await;
    assert_eq!(status, 200, "{original}");
    let revision: i64 = sqlx::query_scalar(
        "select configuration_revision from agent_instance where agent_instance_id=$1",
    )
    .bind(source)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    let proposals = format!("/spaces/{org}/marketplace/proposals");
    let submission = json!({"source_space_id":space,"source_resource_id":source,"kind":"agent","expected_revision":revision.to_string()});
    let (status, proposal) = json_response(
        d.request(
            "writer",
            "POST",
            &proposals,
            Body::from(submission.to_string()),
            "application/json",
            Some(Uuid::new_v4()),
        )
        .await,
    )
    .await;
    assert_eq!(status, 200, "{proposal}");
    assert!(
        proposal["package"]["content"]["capabilities"]["ppt_builder"]["config"]
            .get("analysis_id")
            .is_none()
    );
    assert_eq!(
        d.json(
            "moderator",
            "PUT",
            &format!(
                "{proposals}/{}/decision",
                proposal["proposal_id"].as_str().unwrap()
            ),
            json!({"approve":true,"expected_publication_version":0})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        d.json(
            "writer",
            "DELETE",
            &format!("/spaces/{space}/agent-instances/{source}"),
            json!({})
        )
        .await
        .0,
        202
    );
    let path = format!(
        "/spaces/{org}/marketplace/entries/{}/installations",
        proposal["entry_id"].as_str().unwrap()
    );
    let install = json!({"proposal_id":proposal["proposal_id"],"destination_space_id":space,"options":{"kind":"agent","display_name":"Independent original","logical_name":"independent-original"}});
    let key = Uuid::new_v4();
    let (a, b) = tokio::join!(
        async {
            json_response(
                d.request(
                    "writer",
                    "POST",
                    &path,
                    Body::from(install.to_string()),
                    "application/json",
                    Some(key),
                )
                .await,
            )
            .await
        },
        async {
            json_response(
                d.request(
                    "writer",
                    "POST",
                    &path,
                    Body::from(install.to_string()),
                    "application/json",
                    Some(key),
                )
                .await,
            )
            .await
        }
    );
    assert_eq!(a.0, 200, "{}", a.1);
    assert_eq!(a, b);
    let agent: Uuid = a.1["resource_id"].as_str().unwrap().parse().unwrap();
    let local_path = format!("/spaces/{space}/agent-instances/{agent}");
    assert_eq!(
        d.json("writer", "GET", &local_path, json!(null)).await.1["preparation_state"],
        "pending"
    );
    let (file,prep):(Uuid,Uuid)=sqlx::query_as("select f.id,p.id from powerpoint_file f join capability_preparation p on p.file_id=f.id where f.agent_instance_id=$1 and f.status='stored'").bind(agent).fetch_one(&d.e.pool).await.unwrap();
    assert_ne!(file.to_string(), original["id"]);
    assert_eq!(d.confirm_ppt(prep, None).await.0, 204);
    assert_eq!(
        d.json("writer", "GET", &local_path, json!(null)).await.1["preparation_state"],
        "ready"
    );
    let downloaded = d
        .request(
            "writer",
            "GET",
            &format!(
                "/spaces/{space}/powerpoint-template/{file}/content?agent_instance_id={agent}"
            ),
            Body::empty(),
            "application/json",
            None,
        )
        .await;
    assert_eq!(downloaded.status(), 200);
    assert_eq!(
        to_bytes(downloaded.into_body(), 1000)
            .await
            .unwrap()
            .as_ref(),
        b"frozen configuration original"
    );
}
