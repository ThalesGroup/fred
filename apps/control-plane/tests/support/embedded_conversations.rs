// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::embedded_agent::store::ConversationStore;
use rig_memory::{AsyncStore, LogWriteError};
use std::io::ErrorKind;

async fn conversation(pool: &PgPool) -> (Uuid, Uuid) {
    let org = support::member_organization(pool, "Conversation store", "alice")
        .await
        .unwrap();
    let id = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'control-plane','fred.github.ralph','Ralph','{}','alice','ralph')")
        .bind(id).bind(org.id).execute(pool).await.unwrap();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$1,$1,'control-plane','Ralph',1)")
        .bind(id).bind(org.id).execute(pool).await.unwrap();
    (id, org.id)
}

// Rig's full check_store requires arbitrary log names and writable files. Ralph
// deliberately supports UUID conversation logs only; exercise that log contract
// directly rather than add production file storage solely to satisfy the suite.
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn embedded_log_is_atomic_across_handles_and_checks_expected_length() {
    let e = env().await;
    let (id, _) = conversation(&e.pool).await;
    let name = id.to_string();
    let a = ConversationStore(e.pool.clone());
    let b = a.clone();
    assert_eq!(
        a.read_log_async(&name).await.unwrap_err().kind(),
        ErrorKind::NotFound
    );
    assert!(matches!(
        a.append_log_async(&name, 1, b"lost").await,
        Err(LogWriteError::Changed)
    ));
    assert!(matches!(
        a.replace_log_async(&name, 1, b"lost").await,
        Err(LogWriteError::Changed)
    ));
    let writes =
        futures::future::join_all((0..8).map(|_| a.append_log_async(&name, 0, b"first"))).await;
    assert_eq!(writes.iter().filter(|r| r.is_ok()).count(), 1);
    assert!(
        writes
            .into_iter()
            .filter_map(Result::err)
            .all(|e| matches!(e, LogWriteError::Changed))
    );
    assert_eq!(b.read_log_async(&name).await.unwrap(), b"first");
    b.append_log_async(&name, 5, b" second").await.unwrap();
    assert!(matches!(
        a.append_log_async(&name, 5, b"lost").await,
        Err(LogWriteError::Changed)
    ));
    assert_eq!(a.read_log_async(&name).await.unwrap(), b"first second");
    let (append, replace) = tokio::join!(
        a.append_log_async(&name, 12, b"!"),
        b.replace_log_async(&name, 12, b"replacement")
    );
    assert_ne!(append.is_ok(), replace.is_ok());
    let len = a.read_log_async(&name).await.unwrap().len() as u64;
    a.replace_log_async(&name, len, b"").await.unwrap();
    b.append_log_async(&name, 0, b"again").await.unwrap();
    assert_eq!(a.read_log_async(&name).await.unwrap(), b"again");
    for invalid in ["", "..", "a/b", "not-a-uuid"] {
        assert_eq!(
            a.read_log_async(invalid).await.unwrap_err().kind(),
            ErrorKind::InvalidInput
        );
        assert!(
            matches!(a.append_log_async(invalid, 0, b"x").await, Err(LogWriteError::Io(e)) if e.kind()==ErrorKind::InvalidInput)
        );
    }
    assert_eq!(
        a.read_file_async("image").await.unwrap_err().kind(),
        ErrorKind::Unsupported
    );
    assert_eq!(
        a.write_file_async("image", b"image")
            .await
            .unwrap_err()
            .kind(),
        ErrorKind::Unsupported
    );
    assert_eq!(
        a.write_file_async("../image", b"image")
            .await
            .unwrap_err()
            .kind(),
        ErrorKind::InvalidInput
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn embedded_log_upgrade_retains_retired_content_until_metadata_purge() {
    let mut previous = sqlx::migrate!();
    previous.migrations =
        std::borrow::Cow::Owned(previous.iter().filter(|m| m.version < 6).cloned().collect());
    let pool = environment::database::database_with_migrator(previous).await;
    let (id, space) = conversation(&pool).await;
    sqlx::migrate!().run(&pool).await.unwrap();
    db::require_initialized(&pool).await.unwrap();
    let store = ConversationStore(pool.clone());
    let name = id.to_string();
    store.append_log_async(&name, 0, b"opaque").await.unwrap();
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle
        .accept_session(&pool, "alice", space, id)
        .await
        .unwrap();
    assert_eq!(store.read_log_async(&name).await.unwrap(), b"opaque");
    // An admitted turn may finish during retention. The FK, not an extra admission
    // refresh, prevents writing again once effective purge removed the session.
    store
        .append_log_async(&name, 6, b" retained")
        .await
        .unwrap();
    sqlx::query("delete from session_metadata where session_id=$1")
        .bind(id)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        store.read_log_async(&name).await.unwrap_err().kind(),
        ErrorKind::NotFound
    );
    assert!(
        store
            .append_log_async(&name, 0, b"cannot revive")
            .await
            .is_err()
    );
    sqlx::migrate!().run(&pool).await.unwrap();
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn embedded_history_hides_foreign_retired_and_unreadable_spaces() {
    use control_plane::api::{AppState, routes};
    use serde_json::{Value, json};
    use std::sync::Arc;
    let e = env().await;
    let (id, space) = conversation(&e.pool).await;
    support::member_organization(&e.pool, "Other organization", "bob")
        .await
        .unwrap();
    support::member_organization(&e.pool, "Alice admission survives revocation", "alice")
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    let app = routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle,
    });
    let path = format!("/agents/sessions/{id}/messages");
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        (200, json!([]))
    );
    let foreign = support::request(&app, &identity, Some("bob"), "GET", &path, Value::Null).await;
    let missing = support::request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/agents/sessions/{}/messages", Uuid::new_v4()),
        Value::Null,
    )
    .await;
    assert_eq!(foreign, missing);
    assert_eq!(foreign.0, 404);
    // A format-incompatible log is refused without repair or loss of the bytes.
    let store = ConversationStore(e.pool.clone());
    store
        .append_log_async(&id.to_string(), 0, b"{\"format\":\"rig-session/999\"}\n")
        .await
        .unwrap();
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
            .await
            .0,
        500
    );
    assert_eq!(
        store.read_log_async(&id.to_string()).await.unwrap(),
        b"{\"format\":\"rig-session/999\"}\n"
    );
    // No authorization refresh inside Rig; each history request still needs current access.
    sqlx::query("delete from space_role_grant where space_id=$1 and subject='alice'")
        .bind(space)
        .execute(&e.pool)
        .await
        .unwrap();
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        missing
    );
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'alice','member')")
        .bind(space)
        .execute(&e.pool)
        .await
        .unwrap();
    let (status, _) = support::request(
        &app,
        &identity,
        Some("alice"),
        "DELETE",
        &format!("/spaces/{space}/sessions/{id}"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 202);
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        missing
    );
}
