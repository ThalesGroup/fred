// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::lifecycle::{Lifecycle, Status, cleanup};

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
    cleanup::batch(&e.pool, receipt.id).await.unwrap();
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
        cleanup::batch(&e.pool, receipt.id).await.unwrap();
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
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let capture = AuditCapture::default();
    let _thread =
        tracing::subscriber::set_default(tracing_subscriber::registry().with(capture.clone()));
    for runtime in [fred_rust_agent::DEFINITION.provider, "python"] {
        let id = session(&e, &team, runtime).await;
        let receipt = lifecycle("PT0S")
            .accept_session(&e.pool, "alice", team.id, id)
            .await
            .unwrap();
        cleanup::batch(&e.pool, receipt.id).await.unwrap();
        let events = capture.0.lock().unwrap();
        let accepted = events
            .iter()
            .find(|event| {
                event["audit_event"] == "deletion.accepted" && event["session_id"] == id.to_string()
            })
            .unwrap();
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
        if runtime == fred_rust_agent::DEFINITION.provider {
            let completed = events
                .iter()
                .find(|event| {
                    event["audit_event"] == "deletion.completed"
                        && event["session_id"] == id.to_string()
                })
                .unwrap();
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
    for path in [
        format!("/spaces/{}/sessions/{fresh}", team.id),
        format!("/agents/sessions/{fresh}/messages"),
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
        assert!(matches!(status, 404 | 409), "{path}: {status}");
    }
    cleanup::batch(&e.pool, parent.id).await.unwrap();
    let first: i64 = sqlx::query_scalar(
        "select count(*) from deletion where target_kind='session' and actor_subject='root'",
    )
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert_eq!(first, 100);
    cleanup::batch(&e.pool, parent.id).await.unwrap();
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
        cleanup::batch(&e.pool, child.id).await.unwrap();
    }
    cleanup::batch(&e.pool, parent.id).await.unwrap();
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
    cleanup::batch(&e.pool, old_receipt.id).await.unwrap();
    cleanup::batch(&e.pool, parent.id).await.unwrap();
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
    cleanup::batch(&e.pool, parent.id).await.unwrap();
    let children: Vec<(Uuid, Uuid)> =
        sqlx::query_as("select id,target_id from deletion where target_kind='session'")
            .fetch_all(&e.pool)
            .await
            .unwrap();
    assert_eq!(children.len(), 2);
    for (id, _) in &children {
        cleanup::batch(&e.pool, *id).await.unwrap();
    }
    cleanup::batch(&e.pool, parent.id).await.unwrap();
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
        sqlx::query("insert into document(id,space_id,session_id,name,mime,size,sha256,created_by,object_key,quota_owner) values($1,$2,$3,'attachment.txt','text/plain',1,$4,'alice',$5,$2)")
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
    for _ in 0..10 {
        for candidate in cleanup::candidates(&e.pool, 100).await.unwrap() {
            cleanup::batch(&e.pool, candidate).await.unwrap();
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
