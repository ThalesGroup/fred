// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{
    io::Write,
    sync::{Arc, Mutex},
};

use axum::{body::to_bytes, response::IntoResponse};
use control_plane::error::AppError;
use serde_json::Value;
use uuid::Uuid;

#[path = "support/database.rs"]
mod database;

#[derive(Clone, Default)]
struct Log(Arc<Mutex<Vec<u8>>>);

impl Write for Log {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

async fn response(error: sqlx::Error) -> (u16, Value, String) {
    let log = Log::default();
    let writer = log.clone();
    let subscriber = tracing_subscriber::fmt()
        .without_time()
        .with_ansi(false)
        .with_writer(move || writer.clone())
        .finish();
    // Capture both conversion and rendering: the invariant must log exactly once.
    let response =
        tracing::subscriber::with_default(subscriber, || AppError::from(error).into_response());
    let status = response.status().as_u16();
    let body = to_bytes(response.into_body(), 4096).await.unwrap();
    let logs = String::from_utf8(log.0.lock().unwrap().clone()).unwrap();
    (status, serde_json::from_slice(&body).unwrap(), logs)
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn named_trigger_and_declarative_check_are_private_invariant_problems() {
    let pool = database::database().await;
    let org = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id) values($1,'organization','Original',$1)",
    )
    .bind(org)
    .execute(&pool)
    .await
    .unwrap();
    let error = sqlx::query("update space set organization_id=$2 where id=$1")
        .bind(org)
        .bind(Uuid::new_v4())
        .execute(&pool)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().constraint(),
        Some("space_immutable")
    );
    let (status, body, logs) = response(error).await;
    assert_eq!(status, 500);
    assert_eq!(
        body,
        serde_json::json!({"code":"invariant_violation","detail":"internal error"})
    );
    assert_eq!(logs.matches("invariant_violation").count(), 1);
    assert!(logs.contains("ERROR"));
    assert!(logs.contains("constraint=\"space_immutable\""));
    assert!(logs.contains("table=\"space\""));
    let error =
        sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'local',-1,0,0)")
            .bind(org)
            .execute(&pool)
            .await
            .unwrap_err();
    let constraint = error
        .as_database_error()
        .unwrap()
        .constraint()
        .unwrap()
        .to_owned();
    let (status, body, logs) = response(error).await;
    assert_eq!(status, 500);
    assert_eq!(body["code"], "invariant_violation");
    assert_eq!(body["detail"], "internal error");
    assert!(logs.contains(&constraint));
    assert_eq!(logs.matches("invariant_violation").count(), 1);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn quota_uses_fr001_while_declared_unique_and_foreign_keys_remain_conflicts() {
    let pool = database::database().await;
    let org = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id) values($1,'organization','Unique',$1)",
    )
    .bind(org)
    .execute(&pool)
    .await
    .unwrap();
    sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'local',1,0,0),($1,'organization_total',1,0,0)")
        .bind(org).execute(&pool).await.unwrap();
    let error = sqlx::query("select change_storage_budget($1,0,2)")
        .bind(org)
        .execute(&pool)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("FR001")
    );
    let (status, body, logs) = response(error).await;
    assert_eq!(status, 422);
    assert_eq!(body["code"], "quota_exceeded");
    assert!(logs.is_empty());
    // The custom SQLSTATE is sufficient even if PostgreSQL's message changes.
    let error = sqlx::query(
        "do $$ begin raise exception 'changed quota wording' using errcode='FR001'; end $$",
    )
    .execute(&pool)
    .await
    .unwrap_err();
    let (status, body, _) = response(error).await;
    assert_eq!(status, 422);
    assert_eq!(body["code"], "quota_exceeded");
    let error = sqlx::query(
        "insert into space(id,kind,name,organization_id) values($1,'organization','Unique',$1)",
    )
    .bind(Uuid::new_v4())
    .execute(&pool)
    .await
    .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23505")
    );
    let (status, body, _) = response(error).await;
    assert_eq!(status, 409);
    assert_eq!(body["code"], "conflict");
    let error = sqlx::query(
        "insert into folder(id,space_id,name,path) values($1,$2,'Missing','/missing/')",
    )
    .bind(Uuid::new_v4())
    .bind(Uuid::new_v4())
    .execute(&pool)
    .await
    .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23503")
    );
    let (status, body, _) = response(error).await;
    assert_eq!(status, 409);
    assert_eq!(body["code"], "conflict");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn recent_assertion_triggers_report_constraint_and_table() {
    let pool = database::database().await;
    let org = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id) values($1,'organization','Diagnostics',$1)")
        .bind(org).execute(&pool).await.unwrap();
    // Exercise the effective functions after the full immutable migration chain.
    // All three rows are otherwise valid; only their placement is invalid.
    for (query, constraint, table) in [
        (
            "insert into team_join_link(space_id,token,created_by,expires_at) values($1,gen_random_uuid(),'alice',now()+interval '1 hour')",
            "team_join_link_space_kind",
            "team_join_link",
        ),
        (
            "insert into avatar(id,space_id,object_key,size,status,expires_at) values(gen_random_uuid(),$1,'avatars/test',1,'pending',now()+interval '1 hour')",
            "avatar_space_kind",
            "avatar",
        ),
        (
            "insert into space_model_policy(space_id,revision,updated_by) values($1,1,'alice')",
            "space_model_policy_kind",
            "space_model_policy",
        ),
    ] {
        let error = sqlx::query(query)
            .bind(org)
            .execute(&pool)
            .await
            .unwrap_err();
        assert_invariant_diagnostics(error, constraint, table).await;
    }
    for update in [
        "update application set logical_name='renamed' where id=$1",
        "update application set id=gen_random_uuid() where id=$1",
    ] {
        let mut tx = pool.begin().await.unwrap();
        let id = Uuid::new_v4();
        // The linked offer FK is deferred; this fixture rolls back before commit.
        sqlx::query("insert into application(id,logical_name,ui_base_url,updated_by) values($1,'diagnostics','https://example.test/app/','alice')")
            .bind(id).execute(&mut *tx).await.unwrap();
        let error = sqlx::query(update)
            .bind(id)
            .execute(&mut *tx)
            .await
            .unwrap_err();
        assert_invariant_diagnostics(error, "application_identity", "application").await;
        tx.rollback().await.unwrap();
    }
}

async fn assert_invariant_diagnostics(error: sqlx::Error, constraint: &str, table: &str) {
    let diagnostic = error.as_database_error().unwrap();
    assert_eq!(diagnostic.code().as_deref(), Some("23514"));
    assert_eq!(diagnostic.constraint(), Some(constraint));
    assert_eq!(diagnostic.table(), Some(table));
    let (status, body, logs) = response(error).await;
    assert_eq!(status, 500);
    assert_eq!(
        body,
        serde_json::json!({"code":"invariant_violation","detail":"internal error"})
    );
    assert_eq!(logs.matches("invariant_violation").count(), 1);
    assert!(logs.contains(&format!("constraint=\"{constraint}\"")));
    assert!(logs.contains(&format!("table=\"{table}\"")));
}
