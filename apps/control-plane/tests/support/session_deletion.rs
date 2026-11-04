// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::lifecycle::{Lifecycle, Status, cleanup};

async fn session(e: &Env, team: &Space, runtime: &str) -> Uuid {
    let id = Uuid::new_v4();
    let template =
        control_plane::agents::template_id(team.organization, runtime, fred_rust_agent::AGENT_ID);
    let agent = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$3,$4,$5,'Agent','{}','alice',$6)")
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
