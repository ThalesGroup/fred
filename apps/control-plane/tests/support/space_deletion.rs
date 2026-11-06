// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::lifecycle::{Lifecycle, Status, cleanup, store};
fn immediate() -> Lifecycle {
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    lifecycle
}
async fn drain(e: &Env, id: Uuid) {
    for _ in 0..100 {
        if store::status(&e.pool, "root", id).await.unwrap().status == Status::Completed {
            return;
        }
        cleanup::batch(&e.pool, id, &Default::default(), None)
            .await
            .unwrap();
    }
    panic!("cleanup did not converge");
}

// Proves: I24, I1, I4, I8, I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn lifecycle_authority_retirement_documents_and_durable_receipts() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "P".into(),
        "alice",
    )
    .await
    .unwrap();
    let l = immediate();
    assert!(matches!(
        l.accept(&e.pool, "alice", org.id, false).await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        Lifecycle::default()
            .accept(&e.pool, "root", team.id, false)
            .await,
        Err(AppError::Unavailable(_))
    ));
    let document = Document {
        retrievable: false,
        retrievable_pending: false,
        id: Uuid::new_v4(),
        space_id: project.id,
        folder_id: None,
        name: "d".into(),
        mime: "text/plain".into(),
        size: 0,
        sha256: "a".repeat(64),
        created_by: "alice".into(),
        created_at: chrono::Utc::now(),
    };
    crate::environment::insert_document(&e.pool, &document)
        .await
        .unwrap();
    assert!(matches!(
        l.accept(&e.pool, "root", team.id, false).await,
        Err(AppError::Conflict(_))
    ));
    let count: i64 = sqlx::query_scalar("select count(*) from deletion")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    store::require_active(&e.pool, team.id).await.unwrap();
    sqlx::query("delete from document where id=$1")
        .bind(document.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let receipt = l.accept(&e.pool, "root", team.id, false).await.unwrap();
    assert_eq!(receipt.due_at, receipt.requested_at);
    assert_eq!(
        Lifecycle::default()
            .accept(&e.pool, "root", team.id, false)
            .await
            .unwrap()
            .id,
        receipt.id
    );
    // In-context retirement is reported before the direct permission decision.
    assert!(matches!(
        control_plane::authorization::authorize(&e.pool, "alice", project.id, Permission::Read)
            .await,
        Err(AppError::Problem {
            code: control_plane::lifecycle::store::PENDING_DELETION,
            ..
        })
    ));
    assert!(
        spaces::create_folder(&e.pool, "alice", team.id, None, "blocked".into())
            .await
            .is_err()
    );
    assert!(
        spaces::grant(
            &e.pool,
            &e.subjects(),
            "alice",
            team.id,
            Role::Member,
            "alice"
        )
        .await
        .is_err()
    );
    assert!(l.accept(&e.pool, "root", org.id, false).await.is_err());
    assert!(
        !spaces::memberships(&e.pool, "alice")
            .await
            .unwrap()
            .iter()
            .any(|m| m.space.id == team.id || m.space.id == project.id)
    );
    drain(&e, receipt.id).await;
    let done = l.accept(&e.pool, "root", team.id, false).await.unwrap();
    assert_eq!(done.status, Status::Completed);
    assert_eq!(done.spaces_deleted, 2);
    assert!(db::space(&e.pool, team.id).await.is_err());
    assert!(
        control_plane::authorization::roles_of(&e.pool, "alice")
            .await
            .unwrap()
            .iter()
            .all(|(id, _)| *id == org.id)
    );
    assert!(
        control_plane::authorization::is_platform_admin(&e.pool, "root")
            .await
            .unwrap()
    );
    let recreated = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "BID".into(),
        "alice",
    )
    .await
    .unwrap();
    cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
        .await
        .unwrap();
    assert!(spaces::load(&e.pool, recreated.id).await.is_ok());
}

// Proves: I24, I4, I8
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let sibling = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "Other".into(),
        "alice",
    )
    .await
    .unwrap();
    let l = immediate();
    let first = l.accept(&e.pool, "root", team.id, false).await.unwrap();
    let second = l.accept(&e.pool, "root", sibling.id, false).await.unwrap();
    let doc = Document {
        retrievable: false,
        retrievable_pending: false,
        id: Uuid::new_v4(),
        space_id: team.id,
        folder_id: None,
        name: "unexpected".into(),
        mime: "text/plain".into(),
        size: 0,
        sha256: "a".repeat(64),
        created_by: "fixture".into(),
        created_at: chrono::Utc::now(),
    };
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();
    assert_eq!(cleanup::candidates(&e.pool, 1).await.unwrap(), [first.id]);
    cleanup::batch(&e.pool, first.id, &Default::default(), None)
        .await
        .unwrap();
    let blocked = store::status(&e.pool, "root", first.id).await.unwrap();
    assert_eq!(blocked.status, Status::Blocked);
    assert_eq!(blocked.error_code.as_deref(), Some("unsupported_documents"));
    assert_eq!(cleanup::candidates(&e.pool, 1).await.unwrap(), [second.id]);
    drain(&e, second.id).await;
    sqlx::query("delete from document where id=$1")
        .bind(doc.id)
        .execute(&e.pool)
        .await
        .unwrap();
    drain(&e, first.id).await;
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn project_receipt_lookup_is_read_only_and_bound_to_original_actor() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (_, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "disposable".into(),
        "alice",
    )
    .await
    .unwrap();
    let before: i64 = sqlx::query_scalar("select count(*) from deletion")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert!(
        store::project_status(&e.pool, "root", project.id)
            .await
            .is_err()
    );
    let after: i64 = sqlx::query_scalar("select count(*) from deletion")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(before, after);
    let receipt = immediate()
        .accept(&e.pool, "root", project.id, false)
        .await
        .unwrap();
    assert_eq!(
        store::project_status(&e.pool, "root", project.id)
            .await
            .unwrap()
            .id,
        receipt.id
    );
    assert!(matches!(
        store::project_status(&e.pool, "alice", project.id).await,
        Err(AppError::Forbidden)
    ));
    let mut tx = e.pool.begin().await.unwrap();
    control_plane::authorization::write_platform(
        &mut tx,
        "other",
        control_plane::roles::PlatformRole::PlatformAdmin,
        true,
    )
    .await
    .unwrap();
    tx.commit().await.unwrap();
    assert!(
        store::project_status(&e.pool, "other", project.id)
            .await
            .is_err()
    );
    drain(&e, receipt.id).await;
    assert_eq!(
        store::project_status(&e.pool, "root", project.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn empty_only_folder_deletion_preserves_children_and_retired_documents() {
    use serde_json::Value;
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let parent = spaces::create_folder(&e.pool, "alice", team.id, None, "parent".into())
        .await
        .unwrap();
    let mut writing = hold_organization_lock(&e, org.id).await;
    let child_id = Uuid::new_v4();
    let child = Folder {
        id: child_id,
        space_id: team.id,
        parent_id: Some(parent.id),
        name: "child".into(),
        path: format!("{}{}/", parent.path, child_id),
        created_at: chrono::Utc::now(),
    };
    let pending = {
        let app = app.clone();
        let token = identity.token("alice");
        let path = format!("/folders/{}?empty_only=true", parent.id);
        tokio::spawn(async move { content_request(app, &token, "DELETE", &path, "").await })
    };
    wait_for_advisory_waiter(&e.pool).await;
    db::insert_folder(&mut *writing, &child).await.unwrap();
    writing.commit().await.unwrap();
    assert_eq!(pending.await.unwrap(), 409);
    assert!(db::folder(&e.pool, parent.id).await.is_ok());
    assert!(db::folder(&e.pool, child.id).await.is_ok());
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &format!("/control-plane/v1/folders/{}", parent.id),
            Value::Null
        )
        .await
        .0,
        204
    );
    assert!(db::folder(&e.pool, child.id).await.is_err());
    let parent = spaces::create_folder(&e.pool, "alice", team.id, None, "document-parent".into())
        .await
        .unwrap();
    let document = Document {
        retrievable: false,
        retrievable_pending: false,
        id: Uuid::new_v4(),
        space_id: team.id,
        folder_id: Some(parent.id),
        name: "document".into(),
        mime: "text/plain".into(),
        size: 0,
        sha256: "a".repeat(64),
        created_by: "alice".into(),
        created_at: chrono::Utc::now(),
    };
    crate::environment::insert_document(&e.pool, &document)
        .await
        .unwrap();
    immediate()
        .accept_document(&e.pool, "alice", document.id, None, false)
        .await
        .unwrap();
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &format!("/control-plane/v1/folders/{}?empty_only=true", parent.id),
            Value::Null
        )
        .await
        .0,
        409
    );
    assert!(db::folder(&e.pool, parent.id).await.is_ok());
    assert!(
        sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from document where id=$1 and deletion_id is not null)"
        )
        .bind(document.id)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );
    let empty = spaces::create_folder(&e.pool, "alice", team.id, None, "empty".into())
        .await
        .unwrap();
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &format!("/control-plane/v1/folders/{}?empty_only=true", empty.id),
            Value::Null
        )
        .await
        .0,
        204
    );
}
