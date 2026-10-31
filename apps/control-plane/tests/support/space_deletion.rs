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
        if store::status(&e.pool, &e.authorization, "root", id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            return;
        }
        cleanup::batch(&e.pool, id).await.unwrap();
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
        l.accept(&e.pool, &e.authorization, "alice", org.id).await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        Lifecycle::default()
            .accept(&e.pool, &e.authorization, "root", team.id)
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
        l.accept(&e.pool, &e.authorization, "root", team.id).await,
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
    let receipt = l
        .accept(&e.pool, &e.authorization, "root", team.id)
        .await
        .unwrap();
    assert_eq!(receipt.due_at, receipt.requested_at);
    assert_eq!(
        Lifecycle::default()
            .accept(&e.pool, &e.authorization, "root", team.id)
            .await
            .unwrap()
            .id,
        receipt.id
    );
    // Retirement is reported once the caller is authorized.
    assert!(matches!(
        spaces::authorize(
            &e.pool,
            &e.authorization,
            "alice",
            project.id,
            Permission::Read
        )
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
    assert!(
        l.accept(&e.pool, &e.authorization, "root", org.id)
            .await
            .is_err()
    );
    assert!(
        !spaces::memberships(&e.pool, &e.authorization, "alice")
            .await
            .unwrap()
            .iter()
            .any(|m| m.space.id == team.id || m.space.id == project.id)
    );
    drain(&e, receipt.id).await;
    let done = l
        .accept(&e.pool, &e.authorization, "root", team.id)
        .await
        .unwrap();
    assert_eq!(done.status, Status::Completed);
    assert_eq!(done.spaces_deleted, 2);
    assert!(db::space(&e.pool, team.id).await.is_err());
    assert!(
        e.authorization
            .roles_of("alice")
            .await
            .unwrap()
            .iter()
            .all(|(id, _)| *id == org.id)
    );
    assert!(e.authorization.is_platform_admin("root").await.unwrap());
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
    cleanup::batch(&e.pool, receipt.id).await.unwrap();
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
    let first = l
        .accept(&e.pool, &e.authorization, "root", team.id)
        .await
        .unwrap();
    let second = l
        .accept(&e.pool, &e.authorization, "root", sibling.id)
        .await
        .unwrap();
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
    cleanup::batch(&e.pool, first.id).await.unwrap();
    let blocked = store::status(&e.pool, &e.authorization, "root", first.id)
        .await
        .unwrap();
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
