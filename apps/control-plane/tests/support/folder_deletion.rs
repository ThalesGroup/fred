// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::lifecycle::{Lifecycle, Receipt, Status, cleanup};

fn lifecycle() -> Lifecycle {
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    lifecycle
}

async fn receipt(e: &Env, id: Uuid) -> Receipt {
    sqlx::query_as("select * from deletion where id=$1")
        .bind(id)
        .fetch_one(&e.pool)
        .await
        .unwrap()
}

async fn sweep(e: &Env, id: Uuid) {
    cleanup::batch(&e.pool, id, &Default::default(), None)
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn retired_documents_do_not_reserve_folder_names_or_change_cleanup_ownership() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "writer").await;
    grant(&e, team.id, Role::Editor, "writer").await;
    grant(&e, org.id, Role::Member, "reader").await;
    grant(&e, team.id, Role::Member, "reader").await;
    let l = lifecycle();
    let old = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    let doc = document(team.id, Some(old.id), "same.pdf");
    environment::insert_document(&e.pool, &doc).await.unwrap();
    assert!(matches!(
        l.accept_folder(&e.pool, "writer", old.id, false).await,
        Err(AppError::Conflict(_))
    ));
    let doc_receipt = l
        .accept_document(&e.pool, "writer", doc.id, None, false)
        .await
        .unwrap();
    assert!(matches!(
        l.accept_folder(&e.pool, "reader", old.id, false).await,
        Err(AppError::Forbidden)
    ));
    let retired = l
        .accept_folder(&e.pool, "writer", old.id, true)
        .await
        .unwrap();
    assert!(db::folder(&e.pool, old.id).await.is_err());
    assert!(
        spaces::create_folder(&e.pool, "writer", team.id, Some(old.id), "late".into())
            .await
            .is_err()
    );
    let fresh = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    assert_ne!(fresh.id, old.id);
    assert_ne!(fresh.path, old.path);
    let fresh_doc = document(team.id, Some(fresh.id), "same.pdf");
    environment::insert_document(&e.pool, &fresh_doc)
        .await
        .unwrap();
    assert!(
        spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
            .await
            .is_err()
    );
    sweep(&e, retired.id).await;
    assert_ne!(receipt(&e, retired.id).await.status, Status::Completed);
    assert_eq!(receipt(&e, doc_receipt.id).await.due_at, doc_receipt.due_at);
    assert_eq!(
        sqlx::query_scalar::<_, Uuid>("select deletion_id from document where id=$1")
            .bind(doc.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        doc_receipt.id
    );
    // SQL-only fixture: certify external cleanup, then exercise the real SQL purge.
    sqlx::query("update document set original_cleaned_at=now(),purged_at=now() where id=$1")
        .bind(doc.id)
        .execute(&e.pool)
        .await
        .unwrap();
    sweep(&e, doc_receipt.id).await;
    sweep(&e, retired.id).await;
    sweep(&e, retired.id).await;
    let completed = l
        .accept_folder(&e.pool, "writer", old.id, false)
        .await
        .unwrap();
    assert_eq!(completed.id, retired.id);
    assert_eq!(completed.status, Status::Completed);
    assert_eq!(completed.folders_deleted, 1);
    assert_eq!(completed.documents_deleted, 0);
    assert_eq!(receipt(&e, doc_receipt.id).await.documents_deleted, 1);
    assert_eq!(db::folder(&e.pool, fresh.id).await.unwrap().name, "DRH");
    assert!(db::document(&e.pool, fresh_doc.id).await.is_ok());
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn parent_retirement_preserves_child_receipt_deadline_and_recreated_subtree() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "writer").await;
    grant(&e, team.id, Role::Editor, "writer").await;
    let l = lifecycle();
    let parent = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    let child = spaces::create_folder(&e.pool, "writer", team.id, Some(parent.id), "child".into())
        .await
        .unwrap();
    assert!(matches!(
        l.accept_folder(&e.pool, "writer", parent.id, true).await,
        Err(AppError::Conflict(_))
    ));
    let child_receipt = l
        .accept_folder(&e.pool, "writer", child.id, false)
        .await
        .unwrap();
    sqlx::query("update deletion set due_at=now()+interval '1 hour' where id=$1")
        .bind(child_receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let child_due = receipt(&e, child_receipt.id).await.due_at;
    let parent_receipt = l
        .accept_folder(&e.pool, "writer", parent.id, true)
        .await
        .unwrap();
    assert_eq!(
        l.accept_folder(&e.pool, "writer", child.id, false)
            .await
            .unwrap()
            .id,
        child_receipt.id
    );
    let fresh = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    let fresh_child =
        spaces::create_folder(&e.pool, "writer", team.id, Some(fresh.id), "child".into())
            .await
            .unwrap();
    sweep(&e, parent_receipt.id).await;
    sweep(&e, child_receipt.id).await;
    assert_ne!(
        receipt(&e, parent_receipt.id).await.status,
        Status::Completed
    );
    assert_eq!(receipt(&e, child_receipt.id).await.due_at, child_due);
    sqlx::query("update deletion set due_at=requested_at where id=$1")
        .bind(child_receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    sweep(&e, child_receipt.id).await;
    sweep(&e, parent_receipt.id).await;
    assert_eq!(
        receipt(&e, parent_receipt.id).await.status,
        Status::Completed
    );
    assert_eq!(receipt(&e, parent_receipt.id).await.folders_deleted, 1);
    assert_eq!(receipt(&e, child_receipt.id).await.folders_deleted, 1);
    assert!(db::folder(&e.pool, fresh_child.id).await.is_ok());
    // A space cleanup must not steal a folder job's manifest or retention.
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let retired = l
        .accept_folder(&e.pool, "writer", fresh.id, false)
        .await
        .unwrap();
    let space = l.accept(&e.pool, "root", team.id, false).await.unwrap();
    sweep(&e, space.id).await;
    assert_ne!(receipt(&e, space.id).await.status, Status::Completed);
    sweep(&e, retired.id).await;
    sweep(&e, retired.id).await;
    sweep(&e, space.id).await;
    assert_eq!(receipt(&e, retired.id).await.folders_deleted, 2);
    assert_eq!(receipt(&e, space.id).await.status, Status::Completed);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn folder_purge_waits_for_failed_upload_quiescence_and_cleanup() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "writer").await;
    grant(&e, team.id, Role::Editor, "writer").await;
    let l = lifecycle();
    let folder = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'organization_total',100,0,0),($2,'local',100,0,0) on conflict do nothing")
        .bind(org.id).bind(team.id).execute(&e.pool).await.unwrap();
    let upload = Uuid::new_v4();
    sqlx::query("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,reserved_bytes,put_pending) values($1,$1,'writer',$2,$3,$4,$3,'pending.pdf','application/pdf',1,repeat('a',64),$1::text,'pending',now()+interval '1 hour',1,true)")
        .bind(upload).bind(org.id).bind(team.id).bind(folder.id).execute(&e.pool).await.unwrap();
    assert!(matches!(
        l.accept_folder(&e.pool, "writer", folder.id, false).await,
        Err(AppError::Conflict(_))
    ));
    sqlx::query("update document_upload set status='failed',completed_at=now(),error_code='fixture' where id=$1")
        .bind(upload).execute(&e.pool).await.unwrap();
    let retired = l
        .accept_folder(&e.pool, "writer", folder.id, false)
        .await
        .unwrap();
    let fresh = spaces::create_folder(&e.pool, "writer", team.id, None, "DRH".into())
        .await
        .unwrap();
    sweep(&e, retired.id).await;
    assert_ne!(receipt(&e, retired.id).await.status, Status::Completed);
    // These SQL acknowledgments stand in for the storage worker in this fixture.
    sqlx::query("update document_upload set put_pending=false where id=$1")
        .bind(upload)
        .execute(&e.pool)
        .await
        .unwrap();
    sweep(&e, retired.id).await;
    assert_ne!(receipt(&e, retired.id).await.status, Status::Completed);
    sqlx::query("update document_upload set cleaned_at=now() where id=$1")
        .bind(upload)
        .execute(&e.pool)
        .await
        .unwrap();
    sweep(&e, retired.id).await;
    assert_eq!(receipt(&e, retired.id).await.status, Status::Completed);
    assert!(db::folder(&e.pool, fresh.id).await.is_ok());
    assert!(
        !sqlx::query_scalar::<_, bool>("select exists(select 1 from document_upload where id=$1)")
            .bind(upload)
            .fetch_one(&e.pool)
            .await
            .unwrap()
    );
}
