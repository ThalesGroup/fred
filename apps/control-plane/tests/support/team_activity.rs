// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use chrono::{Duration as ChronoDuration, Utc};
use control_plane::documents::activity::{self, ActivityKind, ActivityQuery, ActivityStatus};

async fn receipt(
    e: &Env,
    space: &Space,
    kind: &str,
    private: bool,
    at: chrono::DateTime<Utc>,
) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into deletion(id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,document_session_id) values($1,$2,$3,$4,$5,'alice',$6,$6,$7)")
        .bind(id).bind(Uuid::new_v4()).bind(kind).bind(space.id).bind(space.organization)
        .bind(at).bind(private.then(Uuid::new_v4)).execute(&e.pool).await.unwrap();
    id
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn team_activity_is_exact_content_scope_even_after_private_target_purge() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let other = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "Other".into(),
        "alice",
    )
    .await
    .unwrap();
    let other_org = crate::support::member_organization(&e.pool, "Foreign", "bob")
        .await
        .unwrap();
    let at = Utc::now() - ChronoDuration::minutes(1);
    let visible = receipt(&e, &team, "document", false, at).await;
    receipt(&e, &team, "document", true, at).await; // Target is already absent: privacy must survive purge.
    receipt(&e, &team, "session", false, at).await;
    receipt(&e, &team, "project", false, at).await;
    receipt(&e, &other, "document", false, at).await;
    receipt(&e, &other_org, "document", false, at).await;
    let page = activity::list(&e.pool, "alice", team.id, ActivityQuery::default())
        .await
        .unwrap();
    assert_eq!(page.items.len(), 1);
    assert_eq!(page.items[0].id, visible);
    assert!(matches!(
        activity::list(&e.pool, "bob", team.id, ActivityQuery::default()).await,
        Err(AppError::NotFound)
    ));
    // Owner and platform privileges never substitute for a direct content role.
    sqlx::query(
        "delete from space_role_grant where space_id=$1 and subject='alice' and role='member'",
    )
    .bind(team.id)
    .execute(&e.pool)
    .await
    .unwrap();
    assert!(matches!(
        activity::list(&e.pool, "alice", team.id, ActivityQuery::default()).await,
        Err(AppError::Forbidden)
    ));
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn team_activity_pages_ties_and_polls_outcomes_without_new_work_displacing_them() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    let at = Utc::now() - ChronoDuration::minutes(1);
    for _ in 0..55 {
        receipt(&e, &team, "folder", false, at).await;
    }
    let first = activity::list(&e.pool, "alice", team.id, ActivityQuery::default())
        .await
        .unwrap();
    assert_eq!(first.items.len(), 50);
    let second = activity::list(
        &e.pool,
        "alice",
        team.id,
        ActivityQuery {
            before: first.next_cursor.clone(),
            until: Some(first.until),
            ..Default::default()
        },
    )
    .await
    .unwrap();
    assert_eq!(second.items.len(), 5);
    assert!(second.next_cursor.is_none());
    assert!(
        !second
            .items
            .iter()
            .any(|row| first.items.iter().any(|old| old.id == row.id))
    );
    let settled = first.items[0].id;
    sqlx::query("update deletion set status='completed',completed_at=now() where id=$1")
        .bind(settled)
        .execute(&e.pool)
        .await
        .unwrap();
    let newer = receipt(&e, &team, "folder", false, Utc::now()).await;
    let poll = activity::list(
        &e.pool,
        "alice",
        team.id,
        ActivityQuery {
            until: Some(first.until),
            ..Default::default()
        },
    )
    .await
    .unwrap();
    assert_eq!(poll.items[0].id, settled);
    assert_eq!(poll.items[0].status, ActivityStatus::Succeeded);
    assert!(!poll.items.iter().any(|row| row.id == newer));
    let latest = activity::list(&e.pool, "alice", team.id, ActivityQuery::default())
        .await
        .unwrap();
    assert_eq!(latest.items[0].id, newer);
    let filtered = activity::list(
        &e.pool,
        "alice",
        team.id,
        ActivityQuery {
            status: Some(ActivityStatus::Succeeded),
            kind: Some(ActivityKind::FolderDeletion),
            ..Default::default()
        },
    )
    .await
    .unwrap();
    assert_eq!(filtered.items.len(), 1);
    assert_eq!(filtered.items[0].id, settled);
    assert!(
        activity::list(
            &e.pool,
            "alice",
            team.id,
            ActivityQuery {
                before: Some("not a cursor".into()),
                ..Default::default()
            }
        )
        .await
        .is_err()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn team_activity_keeps_acknowledged_uploads_and_every_processing_attempt() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let folder = spaces::create_folder(&e.pool, "alice", team.id, None, "Reports".into())
        .await
        .unwrap();
    let doc = document(team.id, Some(folder.id), "report.txt");
    environment::insert_document(&e.pool, &doc).await.unwrap();
    let upload = Uuid::new_v4();
    sqlx::query("insert into document_upload(id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,completed_at,acknowledged_at,target_document_id) values($1,$1,'alice',$2,$3,$4,$3,'report.txt','text/plain',1,$5,$6,'stored',now(),now(),now(),$7)")
        .bind(upload).bind(team.organization).bind(team.id).bind(folder.id).bind("a".repeat(64))
        .bind(format!("upload/{upload}")).bind(doc.id).execute(&e.pool).await.unwrap();
    let failed = Uuid::new_v4();
    let retry = Uuid::new_v4();
    for (id, retry_of, status) in [(failed, None, "failed"), (retry, Some(failed), "pending")] {
        sqlx::query("insert into document_processing(id,request_key,actor,document_id,profile,status,stage,workflow_id,submission,deadline_at,completed_at,error_code,retry_of,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds) values($1,$1,'alice',$2,'fast',$3,'queued',$4,'{}',now()+interval '1 hour',case when $3='failed' then now() end,case when $3='failed' then 'worker_failed' end,$5,'{}',10,10,10)")
            .bind(id).bind(doc.id).bind(status).bind(id.to_string()).bind(retry_of).execute(&e.pool).await.unwrap();
    }
    let page = activity::list(&e.pool, "alice", team.id, ActivityQuery::default())
        .await
        .unwrap();
    assert_eq!(page.items.len(), 3);
    assert!(
        page.items
            .iter()
            .any(|r| r.id == upload && r.status == ActivityStatus::Succeeded)
    );
    assert!(
        page.items
            .iter()
            .any(|r| r.id == failed && r.error_code.as_deref() == Some("worker_failed"))
    );
    assert!(
        page.items
            .iter()
            .any(|r| r.id == retry && r.retry_of == Some(failed))
    );
    sqlx::query("update document_processing set status='failed',error_code='deadline_exceeded',completed_at=now(),revision=revision+1 where id=$1")
        .bind(retry).execute(&e.pool).await.unwrap();
    let poll = activity::list(
        &e.pool,
        "alice",
        team.id,
        ActivityQuery {
            until: Some(page.until),
            ..Default::default()
        },
    )
    .await
    .unwrap();
    assert!(
        poll.items
            .iter()
            .any(|r| r.id == retry && r.status == ActivityStatus::Failed)
    );
    assert_eq!(poll.items.len(), 3);
}
