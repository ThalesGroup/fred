// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use sqlx::{PgPool, postgres::PgConnectOptions};

#[tokio::test]
#[ignore = "needs disposable PostgreSQL with component roles"]
async fn runtime_payload_cascade_requires_no_cross_component_content_access() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let agent = Uuid::new_v4();
    let id = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'python','assistant','Fixture','{}','alice','fixture')")
        .bind(agent).bind(team.id).execute(&e.pool).await.unwrap();
    let insert = "insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$3,'python','Fixture',1)";
    sqlx::query(insert)
        .bind(id)
        .bind(team.id)
        .bind(agent)
        .execute(&e.pool)
        .await
        .unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let base = std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap();
    let options = format!("{base}/{database}")
        .parse::<PgConnectOptions>()
        .unwrap()
        .username("fred_runtime")
        .password("it")
        .options([("search_path", "runtime")]);
    let runtime = PgPool::connect_with(options).await.unwrap();
    sqlx::query("create table runtime.cascade_fixture (session_id uuid primary key references control_plane.session_metadata(session_id) on delete cascade, content text not null)")
        .execute(&runtime).await.unwrap();
    sqlx::query("insert into runtime.cascade_fixture values($1,'private payload')")
        .bind(id)
        .execute(&runtime)
        .await
        .unwrap();
    for query in [
        "select session_id from control_plane.session_metadata",
        "insert into control_plane.session_metadata default values",
        "update control_plane.session_metadata set title='forbidden' where false",
        "delete from control_plane.session_metadata where false",
    ] {
        let error = sqlx::query(query).execute(&runtime).await.unwrap_err();
        assert_eq!(
            error.as_database_error().unwrap().code().as_deref(),
            Some("42501")
        );
    }
    let error = sqlx::query("select content from runtime.cascade_fixture")
        .execute(&e.pool)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("42501")
    );

    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    let receipt = lifecycle
        .accept_session(&e.pool, "alice", team.id, id, false)
        .await
        .unwrap();
    let mut deletion = e.pool.begin().await.unwrap();
    sqlx::query("delete from session_metadata where session_id=$1")
        .bind(id)
        .execute(&mut *deletion)
        .await
        .unwrap();
    // A crash/rollback restores the entire cascade, never just the root.
    deletion.rollback().await.unwrap();
    let retained: String =
        sqlx::query_scalar("select content from runtime.cascade_fixture where session_id=$1")
            .bind(id)
            .fetch_one(&runtime)
            .await
            .unwrap();
    assert_eq!(retained, "private payload");
    let mut deletion = e.pool.begin().await.unwrap();
    sqlx::query("delete from session_metadata where session_id=$1")
        .bind(id)
        .execute(&mut *deletion)
        .await
        .unwrap();
    sqlx::query("update deletion set status='completed',completed_at=now() where id=$1")
        .bind(receipt.id)
        .execute(&mut *deletion)
        .await
        .unwrap();
    deletion.commit().await.unwrap();
    let count: i64 = sqlx::query_scalar("select count(*) from runtime.cascade_fixture")
        .fetch_one(&runtime)
        .await
        .unwrap();
    assert_eq!(count, 0);
    let error = sqlx::query("insert into runtime.cascade_fixture values($1,'late writer')")
        .bind(id)
        .execute(&runtime)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23503")
    );
    let error = sqlx::query(insert)
        .bind(id)
        .bind(team.id)
        .bind(agent)
        .execute(&e.pool)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    let identity = support::IdentityServer::start().await;
    let app = control_plane::api::routes(control_plane::api::AppState {
        history: None,
        pool: e.pool.clone(),
        auth: std::sync::Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        content: None,
        processing: None,
    });
    let response = support::request(&app, &identity, Some("alice"), "POST",
        &format!("/spaces/{}/sessions", team.id),
        serde_json::json!({"session_id":id,"agent_instance_id":agent,"agent_configuration_revision":1})).await;
    assert_eq!(response.0, 404, "{:?}", response.1);
    runtime.close().await;
}
