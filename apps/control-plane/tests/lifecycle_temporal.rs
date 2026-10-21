// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Real API -> durable SQL queue -> separately launched Rust Temporal worker.
use control_plane::{
    api, bootstrap,
    domain::SpaceKind,
    lifecycle::{self, Status, policy::Catalog, worker::SpaceDeletionSweep},
    spaces,
};
use serde_json::json;
use std::{sync::Arc, time::Duration};
use tower::ServiceExt;
use uuid::Uuid;
#[allow(dead_code)]
#[path = "support/environment.rs"]
mod environment;
#[allow(dead_code)]
#[path = "support/mod.rs"]
mod support;
struct Workspace(std::path::PathBuf);
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
fn spawn_worker(config: &std::path::Path, log: &std::path::Path) -> tokio::process::Child {
    tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("worker")
        .env("CONFIG_FILE", config)
        .env("ENV_FILE", "/nonexistent")
        .env("FRED_POSTGRES_PASSWORD", "it")
        .env_remove("OPENFGA_API_TOKEN")
        .kill_on_drop(true)
        .stdout(std::fs::File::create(log).unwrap())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap()
}
async fn wait_for(pool: &sqlx::PgPool, id: Uuid, completed: bool) {
    tokio::time::timeout(Duration::from_secs(90), async {
        loop {
            let (folders, status): (i64, String) =
                sqlx::query_as("select folders_deleted,status from space_deletion where id=$1")
                    .bind(id)
                    .fetch_one(pool)
                    .await
                    .unwrap();
            if if completed {
                status == "completed"
            } else {
                folders > 0 && status != "completed"
            } {
                break;
            }
            tokio::time::sleep(Duration::from_millis(30)).await;
        }
    })
    .await
    .expect("worker progress deadline");
}
// Proves: I24, I4, I8, I23
#[tokio::test]
#[ignore = "needs disposable SQL/OpenFGA/Temporal: make test-lifecycle-temporal"]
async fn api_worker_restart_schedule_reconciliation_and_replay() {
    let host = std::env::var("CONTROL_PLANE_IT_TEMPORAL").expect("make test-lifecycle-temporal");
    let e = environment::env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    let team = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "BID".into(),
        "alice",
    )
    .await
    .unwrap();
    sqlx::query("insert into folder (id,space_id,name,path) select gen_random_uuid(),$1,'folder-'||n,'/' from generate_series(1,1001)n").bind(team.id).execute(&e.pool).await.unwrap();
    let workspace =
        Workspace(std::env::temp_dir().join(format!("fred-lifecycle-{}", Uuid::new_v4())));
    std::fs::create_dir(&workspace.0).unwrap();
    let catalog = workspace.0.join("policy.yaml");
    std::fs::write(&catalog,"version: v1\nspace_policies:\n  purge:\n    default: {mode: deferred_delete, retention: PT2S}\n").unwrap();
    let mut lifecycle = lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.config.sweep_interval = serde_yaml_ng::from_str("PT1S").unwrap();
    lifecycle.config.temporal.host = host;
    lifecycle.config.temporal.task_queue = format!("control-plane-it-{}", Uuid::new_v4());
    lifecycle.config.temporal.workflow_id_prefix = lifecycle.config.temporal.task_queue.clone();
    lifecycle.catalog = Catalog::load(catalog.to_str()).unwrap();
    let identity = support::IdentityServer::start().await;
    let app = api::governance_router(api::AppState {
        auth: Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: None,
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: lifecycle.clone(),
    });
    let response = app
        .oneshot(
            axum::http::Request::builder()
                .method("DELETE")
                .uri(format!("/spaces/{}", team.id))
                .header(
                    "Authorization",
                    format!("Bearer {}", identity.token("root")),
                )
                .body(axum::body::Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 202);
    let body = axum::body::to_bytes(response.into_body(), 10000)
        .await
        .unwrap();
    let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let operation: Uuid = serde_json::from_value(value["id"].clone()).unwrap();
    let pg = temporalio_client::Url::parse(&std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap())
        .unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let t = &lifecycle.config.temporal;
    let config = json!({"app":{"base_url":"/control-plane/v1","address":"127.0.0.1","port":0,"log_format":"json"},
      "security":{"user":{"realm_url":"http://unreachable.invalid","client_id":"unused"},"rebac":{"api_url":e.openfga,"store_name":e.store,"create_store_if_needed":false,"sync_schema_on_init":false}},
      "storage":{"postgres":{"host":pg.host_str(),"port":pg.port().unwrap(),"username":"postgres","database":database}},
      "scheduler":{"lifecycle":{"enabled":true,"sweep_interval":"PT1S","temporal":{"host":t.host,"namespace":t.namespace,"task_queue":t.task_queue,"workflow_id_prefix":t.workflow_id_prefix}}},
      "policies":{"purge_catalog_path":catalog}});
    let config_path = workspace.0.join("config.json");
    std::fs::write(&config_path, serde_json::to_vec(&config).unwrap()).unwrap();
    let client = lifecycle::worker::connect(&lifecycle.config).await.unwrap();
    let mut first = spawn_worker(&config_path, &workspace.0.join("first.log"));
    wait_for(&e.pool, operation, false).await;
    first.kill().await.unwrap();
    first.wait().await.unwrap();
    let receipt = lifecycle::store::status(&e.pool, &e.fga, "root", operation)
        .await
        .unwrap();
    assert_ne!(receipt.status, Status::Completed);
    assert!(chrono::Utc::now() >= receipt.due_at);
    let schedule = client.get_schedule_handle(format!("{}-schedule", t.workflow_id_prefix));
    let history_id = schedule
        .describe(Default::default())
        .await
        .unwrap()
        .recent_actions()
        .last()
        .unwrap()
        .workflow_id
        .clone();
    let mut second = spawn_worker(&config_path, &workspace.0.join("second.log"));
    lifecycle::worker::reconcile(&client, &lifecycle.config)
        .await
        .unwrap();
    wait_for(&e.pool, operation, true).await;
    let done = lifecycle::store::status(&e.pool, &e.fga, "root", operation)
        .await
        .unwrap();
    assert_eq!(done.folders_deleted, 1001);
    assert_eq!(done.spaces_deleted, 1);
    assert!(spaces::load(&e.pool, org.id).await.is_ok());
    let handle = client.get_workflow_handle::<SpaceDeletionSweep>(history_id);
    tokio::time::timeout(
        Duration::from_secs(15),
        handle.get_result(Default::default()),
    )
    .await
    .unwrap()
    .unwrap();
    let replay = temporalio_sdk::workflow_replayer::WorkflowReplayer::new(
        temporalio_sdk::workflow_replayer::WorkflowReplayerOptions::new()
            .register_workflow::<SpaceDeletionSweep>()
            .unwrap()
            .build(),
    )
    .unwrap();
    replay
        .replay_workflow(handle.fetch_history(Default::default()))
        .await
        .unwrap();
    // Hold the platform lock while an activity is pending. SIGTERM must release
    // its local future and server-side wait within the shutdown budget.
    let waiting = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "WAIT".into(),
        "alice",
    )
    .await
    .unwrap();
    let waiting_receipt = lifecycle
        .accept(&e.pool, &e.fga, "root", waiting.id)
        .await
        .unwrap();
    let mut held = e.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(bootstrap::LOCK_KEY)
        .execute(&mut *held)
        .await
        .unwrap();
    tokio::time::timeout(Duration::from_secs(15), async {
        loop {
            let waiting: bool = sqlx::query_scalar("select exists(select 1 from pg_locks where locktype='advisory' and not granted and database=(select oid from pg_database where datname=current_database()))")
                .fetch_one(&e.pool).await.unwrap();
            if waiting { break; }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }).await.expect("activity must wait on the held platform lock");
    assert!(
        tokio::process::Command::new("kill")
            .args(["-TERM", &second.id().unwrap().to_string()])
            .status()
            .await
            .unwrap()
            .success()
    );
    let stopped = tokio::time::timeout(Duration::from_secs(10), second.wait())
        .await
        .expect("bounded graceful shutdown")
        .unwrap();
    assert!(stopped.success());
    tokio::time::timeout(Duration::from_secs(6), async {
        loop {
            let waiting: bool = sqlx::query_scalar("select exists(select 1 from pg_locks where locktype='advisory' and not granted and database=(select oid from pg_database where datname=current_database()))")
                .fetch_one(&e.pool).await.unwrap();
            if !waiting { break; }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }).await.expect("cancelled SQL must release its server-side wait");
    held.rollback().await.unwrap();
    assert_ne!(
        lifecycle::store::status(&e.pool, &e.fga, "root", waiting_receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    let mut third = spawn_worker(&config_path, &workspace.0.join("third.log"));
    wait_for(&e.pool, waiting_receipt.id, true).await;
    // Exhausted retries persist a safe status even without clean-side writes.
    let failing = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "FAIL".into(),
        "alice",
    )
    .await
    .unwrap();
    sqlx::raw_sql("create function fail_lifecycle_test() returns trigger language plpgsql as $$ begin raise exception 'private dependency detail'; end $$; create trigger fail_lifecycle_test before delete on space for each row execute function fail_lifecycle_test()")
        .execute(&e.pool).await.unwrap();
    let failing_receipt = lifecycle
        .accept(&e.pool, &e.fga, "root", failing.id)
        .await
        .unwrap();
    tokio::time::timeout(Duration::from_secs(30), async {
        loop {
            let receipt = lifecycle::store::status(&e.pool, &e.fga, "root", failing_receipt.id)
                .await
                .unwrap();
            if receipt.status == Status::Retrying {
                assert_eq!(
                    receipt.error_code.as_deref(),
                    Some("dependency_unavailable")
                );
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await
    .expect("workflow exhaustion must persist retrying");
    sqlx::query("drop trigger fail_lifecycle_test on space")
        .execute(&e.pool)
        .await
        .unwrap();
    wait_for(&e.pool, failing_receipt.id, true).await;
    third.kill().await.unwrap();
    third.wait().await.unwrap();
    let mut disabled = lifecycle.config.clone();
    disabled.enabled = false;
    lifecycle::worker::reconcile(&client, &disabled)
        .await
        .unwrap();
    assert!(
        schedule
            .describe(Default::default())
            .await
            .unwrap()
            .paused()
    );
    schedule.delete(Default::default()).await.unwrap();
    for name in ["first.log", "second.log", "third.log"] {
        let log = std::fs::read_to_string(workspace.0.join(name)).unwrap();
        assert!(log.contains("\"service_role\":\"worker\""));
        assert!(!log.contains("Bearer "));
        assert!(!log.contains("private dependency detail"));
        if name == "first.log" {
            assert!(!log.contains("space.deletion.completed"));
        } else {
            assert!(log.contains("\"audit_event\":\"space.deletion.completed\""));
        }
    }
}
