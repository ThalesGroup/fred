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

        let observed = control_plane::authorization::Authorization::new(e.pool.clone());
        let storage = Storage::start(
            &e.pool,
            &observed,
            None,
            config,
            "fixture-access".into(),
            "fixture-secret".into(),
        )
        .await
        .unwrap();
        let identity = crate::support::IdentityServer::start().await;
        let app = api::router(
            api::AppState {
                agent_catalog: Default::default(),
                pool: e.pool.clone(),
                authorization: observed,
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
    let (id, key): (Uuid, String) = sqlx::query_as("select id,object_key from document")
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
                &d.e.authorization,
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
                    authorization: d.e.authorization.clone(),
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
    for user in ["reader", "analyst", "owner", "stranger"] {
        let (status, body) = d
            .upload(user, "denied.txt", b"bytes", Uuid::new_v4(), None)
            .await;
        assert_eq!(
            status,
            if user == "stranger" { 404 } else { 403 },
            "{user}: {body}"
        );
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
    for user in ["owner", "stranger"] {
        assert_eq!(
            d.json(
                user,
                "GET",
                &format!("/documents/{id}/content"),
                Value::Null
            )
            .await
            .0,
            if user == "owner" { 403 } else { 404 }
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
    assert!(cleaned);
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
    let ready: String = sqlx::query_scalar("select object_key from document")
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
    assert_eq!(status, 201, "{receipt}");
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
    let peer =
        crate::support::member_organization(&d.e.pool, &d.e.authorization, "Peer", "peer-owner")
            .await
            .unwrap();
    let id = Uuid::new_v4();
    let failed = Uuid::new_v4();
    let pending_key:String=sqlx::query_scalar("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at) select $1,$1,actor,organization_id,space_id,folder_id,quota_owner,'pending.txt',mime,size,sha256,replace(object_key,id::text,$1::text),'pending',clock_timestamp()-interval '1 second' from document_upload where status='stored' returning object_key")
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
    let (document, original): (Uuid, String) = sqlx::query_as("select id,object_key from document")
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
