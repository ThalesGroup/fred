// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::lifecycle::{Lifecycle, Status, cleanup};
use serde_json::json;

async fn session(e: &Env, team: &Space, runtime: &str) -> Uuid {
    let id = Uuid::new_v4();
    let template =
        control_plane::agents::template_id(team.organization, runtime, fred_rust_agent::AGENT_ID);
    let agent = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$3,$4,$5,$6,'{}','alice',$6)")
        .bind(agent).bind(team.id).bind(template).bind(runtime).bind(fred_rust_agent::AGENT_ID).bind(format!("agent-{agent}")).execute(&e.pool).await.unwrap();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$4,$5,'Agent',1)")
        .bind(id).bind(team.id).bind(agent).bind(template).bind(runtime).execute(&e.pool).await.unwrap();
    id
}
fn lifecycle(retention: &str) -> Lifecycle {
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str(retention).unwrap();
    lifecycle
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn embedded_session_purge_observes_retention_and_is_idempotent() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let id = session(&e, &team, fred_rust_agent::DEFINITION.provider).await;
    sqlx::query("insert into embedded_agent_conversation(session_id,log) values($1,$2)")
        .bind(id)
        .bind(b"retained log".as_slice())
        .execute(&e.pool)
        .await
        .unwrap();
    let receipt = lifecycle("P7D")
        .accept_session(&e.pool, "alice", team.id, id)
        .await
        .unwrap();
    cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
        .await
        .unwrap();
    let before: i64 =
        sqlx::query_scalar("select count(*) from embedded_agent_conversation where session_id=$1")
            .bind(id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(before, 1);
    sqlx::query("update deletion set due_at=now() where id=$1")
        .bind(receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    for _ in 0..2 {
        cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
            .await
            .unwrap();
    }
    let status: Status = sqlx::query_scalar("select status from deletion where id=$1")
        .bind(receipt.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(status, Status::Completed);
    for table in ["session_metadata", "embedded_agent_conversation"] {
        let count: i64 = sqlx::query_scalar(AssertSqlSafe(format!(
            "select count(*) from {table} where session_id=$1"
        )))
        .bind(id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
        assert_eq!(count, 0);
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn session_deletion_audit_has_runtime_independent_provenance() {
    use tracing::instrument::WithSubscriber;
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let pod = PythonPurge::start(e.pool.clone()).await;
    let capture = AuditCapture::default();
    let subscriber = tracing_subscriber::registry().with(capture.clone());
    async {
        for runtime in [fred_rust_agent::DEFINITION.provider, "python"] {
            let id = session(&e, &team, runtime).await;
            let receipt = lifecycle("PT0S")
                .accept_session(&e.pool, "alice", team.id, id)
                .await
                .unwrap();
            cleanup::batch(&e.pool, receipt.id, &pod.runtime, None)
                .await
                .unwrap();
            {
                let status: Status = sqlx::query_scalar("select status from deletion where id=$1")
                    .bind(receipt.id)
                    .fetch_one(&e.pool)
                    .await
                    .unwrap();
                assert_eq!(status, Status::Completed);
            }
            let events = capture.0.lock().unwrap();
            let accepted = events
                .iter()
                .find(|event| {
                    event["audit_event"] == "deletion.accepted"
                        && event["session_id"] == id.to_string()
                })
                .unwrap_or_else(|| panic!("missing acceptance: {events:?}"));
            for field in [
                "operation_id",
                "session_id",
                "space_id",
                "organization_id",
                "actor_uid",
                "runtime_id",
                "rule_id",
                "requested_at",
                "due_at",
            ] {
                assert!(accepted.get(field).is_some(), "missing {field}: {accepted}");
            }
            assert_eq!(accepted["space_id"], team.id.to_string());
            assert_eq!(accepted["runtime_id"], runtime);
            {
                let completed = events
                    .iter()
                    .find(|event| {
                        event["audit_event"] == "deletion.completed"
                            && event["session_id"] == id.to_string()
                    })
                    .unwrap_or_else(|| panic!("missing completion: {events:?}"));
                for field in [
                    "operation_id",
                    "session_id",
                    "space_id",
                    "organization_id",
                    "actor_uid",
                    "runtime_id",
                    "rule_id",
                    "requested_at",
                    "due_at",
                ] {
                    assert_eq!(accepted[field], completed[field]);
                }
                assert!(completed.get("completed_at").is_some());
            }
        }
    }
    .with_subscriber(subscriber)
    .await;
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn team_retirement_hides_sessions_before_bounded_receipts_and_preserves_retention() {
    use control_plane::api::{AppState, routes};
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (_, team) = org_and_team(&e).await;
    let old = session(&e, &team, fred_rust_agent::DEFINITION.provider).await;
    let old_receipt = lifecycle("P7D")
        .accept_session(&e.pool, "alice", team.id, old)
        .await
        .unwrap();
    let fresh = session(&e, &team, fred_rust_agent::DEFINITION.provider).await;
    // 101 fresh conversations prove one visit never materializes an unbounded manifest.
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) select gen_random_uuid(),user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision from session_metadata cross join generate_series(1,100) where session_id=$1")
        .bind(fresh).execute(&e.pool).await.unwrap();
    let parent = lifecycle("PT0S")
        .accept(&e.pool, "root", team.id)
        .await
        .unwrap();
    let still_unmarked: Option<Uuid> =
        sqlx::query_scalar("select deletion_id from session_metadata where session_id=$1")
            .bind(fresh)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(still_unmarked, None);
    let identity = support::IdentityServer::start().await;
    let app = routes(AppState {
        pool: e.pool.clone(),
        auth: std::sync::Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        content: None,
        processing: None,
    });
    for (path, expected) in [
        (format!("/spaces/{}/sessions/{fresh}", team.id), 409),
        (format!("/agents/sessions/{fresh}/messages"), 404),
    ] {
        let (status, _) = support::request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &path,
            serde_json::Value::Null,
        )
        .await;
        assert_eq!(status, expected, "{path}");
    }
    cleanup::batch(&e.pool, parent.id, &Default::default(), None)
        .await
        .unwrap();
    let first: i64 = sqlx::query_scalar(
        "select count(*) from deletion where target_kind='session' and actor_subject='root'",
    )
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert_eq!(first, 100);
    cleanup::batch(&e.pool, parent.id, &Default::default(), None)
        .await
        .unwrap();
    let children: Vec<control_plane::lifecycle::Receipt> = sqlx::query_as(
        "select * from deletion where target_kind='session' and actor_subject='root'",
    )
    .fetch_all(&e.pool)
    .await
    .unwrap();
    assert_eq!(children.len(), 101);
    for child in &children {
        assert_eq!(child.requested_at, parent.requested_at);
        assert_eq!(child.due_at, parent.due_at);
        cleanup::batch(&e.pool, child.id, &Default::default(), None)
            .await
            .unwrap();
    }
    cleanup::batch(&e.pool, parent.id, &Default::default(), None)
        .await
        .unwrap();
    let retained: control_plane::lifecycle::Receipt =
        sqlx::query_as("select * from deletion where id=$1")
            .bind(old_receipt.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(retained.due_at, old_receipt.due_at);
    assert!(db::space(&e.pool, team.id).await.is_ok());
    sqlx::query("update deletion set due_at=now() where id=$1")
        .bind(old_receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    cleanup::batch(&e.pool, old_receipt.id, &Default::default(), None)
        .await
        .unwrap();
    cleanup::batch(&e.pool, parent.id, &Default::default(), None)
        .await
        .unwrap();
    let status: Status = sqlx::query_scalar("select status from deletion where id=$1")
        .bind(parent.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(status, Status::Completed);
    assert!(db::space(&e.pool, team.id).await.is_err());
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn organization_retirement_keeps_python_conversations_and_their_space_until_safe_purge() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    let ralph = session(&e, &team, fred_rust_agent::DEFINITION.provider).await;
    let python = session(&e, &project, "python").await;
    let parent = lifecycle("PT0S")
        .accept(&e.pool, "root", org.id)
        .await
        .unwrap();
    for _ in 0..2 {
        cleanup::batch(&e.pool, parent.id, &Default::default(), None)
            .await
            .unwrap();
    }
    let children: Vec<(Uuid, Uuid)> =
        sqlx::query_as("select id,target_id from deletion where target_kind='session'")
            .fetch_all(&e.pool)
            .await
            .unwrap();
    assert_eq!(children.len(), 2);
    for (id, _) in &children {
        cleanup::batch(&e.pool, *id, &Default::default(), None)
            .await
            .unwrap();
    }
    cleanup::batch(&e.pool, parent.id, &Default::default(), None)
        .await
        .unwrap();
    let remains: Vec<Uuid> = sqlx::query_scalar("select session_id from session_metadata")
        .fetch_all(&e.pool)
        .await
        .unwrap();
    assert_eq!(remains, vec![python]);
    assert!(!remains.contains(&ralph));
    let python_receipt = children
        .iter()
        .find(|(_, session)| *session == python)
        .unwrap()
        .0;
    let blocked: (Status, Option<String>) =
        sqlx::query_as("select status,error_code from deletion where id=$1")
            .bind(python_receipt)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(
        blocked,
        (Status::Blocked, Some("session_purge_unavailable".into()))
    );
    assert!(db::space(&e.pool, org.id).await.is_ok());
    assert!(db::space(&e.pool, project.id).await.is_ok());
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn organization_purge_drains_conversations_and_attachments_in_teams_projects_and_personal_spaces()
 {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    for space in [&team, &project, &personal] {
        let conversation = session(&e, space, fred_rust_agent::DEFINITION.provider).await;
        sqlx::query("select fixture_document(p_id=>$1,p_space_id=>$2,p_session_id=>$3,p_name=>'attachment.txt',p_mime=>'text/plain',p_size=>1,p_sha256=>$4,p_created_by=>'alice',p_object_key=>$5,p_quota_owner=>$2)")
            .bind(Uuid::new_v4()).bind(space.id).bind(conversation).bind("a".repeat(64)).bind(format!("fixture/{conversation}")).execute(&e.pool).await.unwrap();
    }
    let parent = lifecycle("PT0S")
        .accept(&e.pool, "root", org.id)
        .await
        .unwrap();
    let retired_attachments: i64 =
        sqlx::query_scalar("select count(*) from document where deletion_id=$1")
            .bind(parent.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(retired_attachments, 3);
    // This hierarchy fixture creates SQL manifests only, with no object store.
    // Physical original deletion is covered by document-storage integration tests.
    sqlx::query("update document set original_cleaned_at=now() where deletion_id=$1")
        .bind(parent.id)
        .execute(&e.pool)
        .await
        .unwrap();
    for _ in 0..10 {
        for candidate in cleanup::candidates(&e.pool, 100).await.unwrap() {
            cleanup::batch(&e.pool, candidate, &Default::default(), None)
                .await
                .unwrap();
        }
    }
    let done: control_plane::lifecycle::Receipt =
        sqlx::query_as("select * from deletion where id=$1")
            .bind(parent.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(done.status, Status::Completed);
    assert_eq!(done.spaces_deleted, 4);
    assert_eq!(done.documents_deleted, 3);
    let remains: bool = sqlx::query_scalar(
        "select exists(select 1 from session_metadata) or exists(select 1 from document)",
    )
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert!(!remains);
}

struct PythonPurge {
    runtime: control_plane::lifecycle::runtime_storage::RuntimeStorage,
    status: std::sync::Arc<std::sync::atomic::AtomicU16>,
    purged: std::sync::Arc<std::sync::atomic::AtomicBool>,
    calls: std::sync::Arc<std::sync::atomic::AtomicUsize>,
    gate: std::sync::Arc<support::Gate>,
    pause: std::sync::Arc<std::sync::atomic::AtomicBool>,
    task: tokio::task::JoinHandle<()>,
    _identity: support::IdentityServer,
}
impl Drop for PythonPurge {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl PythonPurge {
    async fn start(pool: sqlx::PgPool) -> Self {
        use std::sync::{
            Arc,
            atomic::{AtomicBool, AtomicU16, AtomicUsize, Ordering},
        };
        let identity = support::IdentityServer::start().await;
        let status = Arc::new(AtomicU16::new(200));
        let purged = Arc::new(AtomicBool::new(true));
        let calls = Arc::new(AtomicUsize::new(0));
        let pause = Arc::new(AtomicBool::new(false));
        let gate = Arc::new(support::Gate::default());
        let app = axum::Router::new().route(
            "/private/agents/sessions/{session}",
            axum::routing::delete({
                let (status, purged, calls, pause, gate) = (
                    status.clone(),
                    purged.clone(),
                    calls.clone(),
                    pause.clone(),
                    gate.clone(),
                );
                move |headers: axum::http::HeaderMap| {
                    let (status, purged, calls, pause, gate, pool) = (
                        status.clone(),
                        purged.clone(),
                        calls.clone(),
                        pause.clone(),
                        gate.clone(),
                        pool.clone(),
                    );
                    async move {
                        assert_eq!(headers["authorization"], "Bearer service-token");
                        // The lifecycle's global lock must be released during HTTP.
                        let mut tx = pool.begin().await.unwrap();
                        let free: bool = sqlx::query_scalar("select pg_try_advisory_xact_lock($1)")
                            .bind(bootstrap::LOCK_KEY)
                            .fetch_one(&mut *tx)
                            .await
                            .unwrap();
                        assert!(
                            free,
                            "runtime purge must not run inside the lifecycle SQL transaction"
                        );
                        tx.rollback().await.unwrap();
                        calls.fetch_add(1, Ordering::SeqCst);
                        gate.entered.notify_one();
                        if pause.load(Ordering::SeqCst) {
                            gate.release.notified().await;
                        }
                        (
                            axum::http::StatusCode::from_u16(status.load(Ordering::SeqCst))
                                .unwrap(),
                            axum::Json(
                                if status.load(Ordering::SeqCst) == 503
                                    && purged.load(Ordering::SeqCst)
                                {
                                    json!({"detail":"session_writes_pending"})
                                } else if purged.load(Ordering::SeqCst) {
                                    json!({"purged":true})
                                } else {
                                    json!({"deleted":3})
                                },
                            ),
                        )
                    }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let runtime = control_plane::lifecycle::runtime_storage::RuntimeStorage {
            directory: Some(identity.directory()),
            sources: vec![control_plane::agents::RuntimeCatalogSource {
                runtime_id: "python".into(),
                base_url: format!("http://{address}/private"),
                public_base_url: Some("/browser-must-not-be-used".into()),
                enabled: true,
            }],
        };
        Self {
            runtime,
            status,
            purged,
            calls,
            gate,
            pause,
            task,
            _identity: identity,
        }
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn python_purge_retries_blocked_receipts_and_requires_effective_erasure() {
    use std::sync::atomic::Ordering;
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let id = session(&e, &team, "python").await;
    let untouched = session(&e, &team, "python").await;
    let receipt = lifecycle("PT0S")
        .accept_session(&e.pool, "alice", team.id, id)
        .await
        .unwrap();
    cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
        .await
        .unwrap();
    assert!(
        cleanup::candidates(&e.pool, 100)
            .await
            .unwrap()
            .contains(&receipt.id)
    );
    let pod = PythonPurge::start(e.pool.clone()).await;
    // Disabled sources cannot trigger a call, even when they have a URL.
    let mut disabled = pod.runtime.clone();
    disabled.sources[0].enabled = false;
    cleanup::batch(&e.pool, receipt.id, &disabled, None)
        .await
        .unwrap();
    assert_eq!(pod.calls.load(Ordering::SeqCst), 0);
    pod.purged.store(false, Ordering::SeqCst);
    for status in [503, 404, 401, 302] {
        pod.status.store(status, Ordering::SeqCst);
        assert!(
            cleanup::batch(&e.pool, receipt.id, &pod.runtime, None)
                .await
                .is_err()
        );
        cleanup::retrying(&e.pool, receipt.id).await.unwrap();
        let exists: bool =
            sqlx::query_scalar("select exists(select 1 from session_metadata where session_id=$1)")
                .bind(id)
                .fetch_one(&e.pool)
                .await
                .unwrap();
        assert!(exists);
    }
    pod.status.store(503, Ordering::SeqCst);
    pod.purged.store(true, Ordering::SeqCst);
    cleanup::batch(&e.pool, receipt.id, &pod.runtime, None)
        .await
        .unwrap();
    let reason: String = sqlx::query_scalar("select error_code from deletion where id=$1")
        .bind(receipt.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(reason, "session_writes_pending");
    pod.status.store(200, Ordering::SeqCst);
    pod.purged.store(false, Ordering::SeqCst);
    assert!(
        cleanup::batch(&e.pool, receipt.id, &pod.runtime, None)
            .await
            .is_err(),
        "a success without an explicit purge acknowledgement must not complete erasure"
    );
    pod.purged.store(true, Ordering::SeqCst);
    for _ in 0..2 {
        cleanup::batch(&e.pool, receipt.id, &pod.runtime, None)
            .await
            .unwrap();
    }
    assert_eq!(pod.calls.load(Ordering::SeqCst), 7);
    let status: Status = sqlx::query_scalar("select status from deletion where id=$1")
        .bind(receipt.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(status, Status::Completed);
    let remaining: Vec<Uuid> = sqlx::query_scalar("select session_id from session_metadata")
        .fetch_all(&e.pool)
        .await
        .unwrap();
    assert_eq!(remaining, vec![untouched]);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn python_purge_resumes_after_cancelled_call_and_unblocks_parent_deletion() {
    use std::sync::atomic::Ordering;
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let id = session(&e, &team, "python").await;
    let parent = lifecycle("PT0S")
        .accept(&e.pool, "root", org.id)
        .await
        .unwrap();
    let pod = PythonPurge::start(e.pool.clone()).await;
    cleanup::batch(&e.pool, parent.id, &pod.runtime, None)
        .await
        .unwrap();
    let receipt: Uuid = sqlx::query_scalar("select id from deletion where target_id=$1")
        .bind(id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    pod.pause.store(true, Ordering::SeqCst);
    let task = tokio::spawn({
        let pool = e.pool.clone();
        let runtime = pod.runtime.clone();
        async move { cleanup::batch(&pool, receipt, &runtime, None).await }
    });
    pod.gate.entered.notified().await;
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    pod.pause.store(false, Ordering::SeqCst);
    pod.gate.release.notify_one();
    // Fresh activity state retries an ambiguous call, then parent sweeps progress.
    let runtime = pod.runtime.clone();
    for _ in 0..5 {
        for candidate in cleanup::candidates(&e.pool, 100).await.unwrap() {
            cleanup::batch(&e.pool, candidate, &runtime, None)
                .await
                .unwrap();
        }
    }
    let status: Status = sqlx::query_scalar("select status from deletion where id=$1")
        .bind(parent.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(status, Status::Completed);
    assert_eq!(pod.calls.load(Ordering::SeqCst), 2);
    assert!(db::space(&e.pool, org.id).await.is_err());
}
