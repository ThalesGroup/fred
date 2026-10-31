// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use axum::{
    body::{Body, to_bytes},
    http::Request,
};
use control_plane::api::{AppState, routes};
use serde_json::{Value, json};
use std::{collections::BTreeSet, sync::Arc};
use tower::ServiceExt;

async fn request(
    app: &axum::Router,
    identity: &support::IdentityServer,
    actor: Option<&str>,
    method: &str,
    path: &str,
    body: Value,
) -> (u16, Value) {
    let mut req = Request::builder()
        .method(method)
        .uri(path)
        .header("content-type", "application/json");
    if let Some(actor) = actor {
        req = req.header("authorization", format!("Bearer {}", identity.token(actor)));
    }
    let response = app
        .clone()
        .oneshot(req.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    let status = response.status().as_u16();
    let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    (status, serde_json::from_slice(&body).unwrap_or(Value::Null))
}
async fn state(
    e: &Env,
    identity: &support::IdentityServer,
    authorization: Authorization,
) -> AppState {
    AppState {
        agent_catalog: Default::default(),
        pool: e.pool.clone(),
        authorization,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    }
}

// Proves: I5, I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn organization_console_rechecks_waiting_creator_and_serializes_attachment() {
    use control_plane::roles::PlatformRole;
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    identity
        .users
        .lock()
        .await
        .insert("target".into(), "target".into());
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    control_plane::authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "delegate",
        PlatformRole::PlatformAdmin,
        true,
    )
    .await
    .unwrap();
    let mut tx = e.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(bootstrap::LOCK_KEY)
        .execute(&mut *tx)
        .await
        .unwrap();
    let (pool, authorization, directory) = (
        e.pool.clone(),
        e.authorization.clone(),
        identity.directory(),
    );
    let pending = tokio::spawn(async move {
        spaces::create_managed_organization(
            &pool,
            &authorization,
            &control_plane::users::Directory::Keycloak(Some(&directory)),
            "delegate",
            "Revoked",
            "target",
            "target",
        )
        .await
    });
    wait_for_advisory_waiter(&e.pool).await;
    delete_tuple(&e, "delegate", "platform_admin", "platform:root").await;
    tx.commit().await.unwrap();
    assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
    assert!(
        db::organization_named(&e.pool, "Revoked")
            .await
            .unwrap()
            .is_none()
    );
    let directory = identity.directory();
    let resolver = control_plane::users::Directory::Keycloak(Some(&directory));
    let (a, b) = tokio::join!(
        spaces::create_managed_organization(
            &e.pool,
            &e.authorization,
            &resolver,
            "root",
            "One",
            "target",
            "target"
        ),
        spaces::create_managed_organization(
            &e.pool,
            &e.authorization,
            &resolver,
            "root",
            "Two",
            "target",
            "target"
        )
    );
    assert_ne!(a.is_ok(), b.is_ok());
    assert!(matches!(a.err().or(b.err()), Some(AppError::Conflict(_))));
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn supervision_team_pagination_preserves_full_totals() {
    let e = env().await;
    let (org, first) = org_and_team(&e).await;
    // Metadata-only fixtures; no grants are required for an empty collective team.
    let mut expected = BTreeSet::from([first.id]);
    for index in 0..101 {
        let id = Uuid::new_v4();
        sqlx::query(
            "insert into space(id,kind,name,organization_id,parent_id) values($1,'team',$2,$3,$3)",
        )
        .bind(id)
        .bind(format!("Page team {index}"))
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap();
        expected.insert(id);
    }
    environment::insert_document(&e.pool, &document(first.id, None, "one.txt"))
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let app = routes(state(&e, &identity, e.authorization.clone()).await);
    let path = format!("/organizations/{}/supervision", org.id);
    let (status, first) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{first}");
    assert_eq!(first["active_teams"], 102);
    assert_eq!(first["teams"]["items"].as_array().unwrap().len(), 100);
    let cursor = first["teams"]["next_cursor"].as_str().unwrap();
    let (status, second) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &format!("{path}?after={cursor}"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{second}");
    assert_eq!(first["totals"], second["totals"]);
    assert_eq!(first["teams_total"], second["teams_total"]);
    assert_eq!(second["teams"]["items"].as_array().unwrap().len(), 2);
    assert!(second["teams"]["next_cursor"].is_null());
    let actual: BTreeSet<_> = first["teams"]["items"]
        .as_array()
        .unwrap()
        .iter()
        .chain(second["teams"]["items"].as_array().unwrap())
        .map(|t| Uuid::parse_str(t["id"].as_str().unwrap()).unwrap())
        .collect();
    assert_eq!(actual, expected);
}

/// Controlled SQL history, including success followed by failure: this is a
/// selection contract fixture, not a claim that admit permits reprocessing success.
async fn supervision_attempt(
    e: &Env,
    doc: &Document,
    status: &str,
    parquet_paths: Option<&[&str]>,
    rows: Option<i64>,
) {
    let id = Uuid::new_v4();
    sqlx::query(
        "insert into document_processing(
        id,request_key,actor,document_id,profile,workflow_id,submission,profile_settings,
        deadline_at,status,stage,completed_at,preparation_seconds,extraction_seconds,indexing_seconds)
        values($1,$1,'alice',$2,'fast',$3,'{}','{}',now()+interval '1 hour',
        $4,case when $4='pending' then 'queued' else 'done' end,
        case when $4 in ('failed','succeeded') then now() end,60,60,60)",
    )
    .bind(id)
    .bind(doc.id)
    .bind(id.to_string())
    .bind(status)
    .execute(&e.pool)
    .await
    .unwrap();
    let Some(paths) = parquet_paths else {
        return;
    };
    let generation = Uuid::new_v4();
    sqlx::query(
        "insert into generation(id,processing_id,stage,execution_id,activity_id,attempt,
        expires_at,prefix,committed_at,chunks,vector_ordinals,rows,cleanup_after,document_id)
        values($1,$2,'indexing',$1,$1,1,now(),'fixture/',now(),7,'{0,1,2}',$3,now(),$4)",
    )
    .bind(generation)
    .bind(id)
    .bind(rows)
    .bind(doc.id)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query(
        "insert into artifact select $1, path, 1, repeat('a', 64) from unnest($2::text[]) path",
    )
    .bind(generation)
    .bind(paths)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query("update document set published_generation=$2 where id=$1")
        .bind(doc.id)
        .bind(generation)
        .execute(&e.pool)
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn supervision_separates_attempts_publications_unknown_rows_and_purge() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    for (name, paths, rows) in [
        ("published", vec!["datasets/a.parquet"], Some(12)),
        ("zero", vec!["datasets/b.parquet"], Some(0)),
        ("unknown", vec!["datasets/c.parquet"], None),
        (
            "multiple",
            vec!["datasets/d.parquet", "datasets/e.parquet"],
            Some(99),
        ),
    ] {
        let doc = document(team.id, None, name);
        environment::insert_document(&e.pool, &doc).await.unwrap();
        supervision_attempt(&e, &doc, "succeeded", Some(&paths), rows).await;
        if name == "published" {
            supervision_attempt(&e, &doc, "failed", None, None).await;
        }
    }
    let retry = document(team.id, None, "retry");
    environment::insert_document(&e.pool, &retry).await.unwrap();
    supervision_attempt(&e, &retry, "failed", None, None).await;
    supervision_attempt(&e, &retry, "pending", None, None).await;
    let retired = document(team.id, None, "retired");
    environment::insert_document(&e.pool, &retired)
        .await
        .unwrap();
    supervision_attempt(
        &e,
        &retired,
        "succeeded",
        Some(&["datasets/retired.parquet"]),
        Some(1000),
    )
    .await;
    let deletion = Uuid::new_v4();
    sqlx::query(
        "insert into deletion(id,target_id,target_kind,target_parent_id,
        organization_id,actor_subject,requested_at,due_at)
        values($1,$2,'document',$3,$4,'alice',now(),now())",
    )
    .bind(deletion)
    .bind(retired.id)
    .bind(team.id)
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query("update document set deletion_id=$1,purge_after=clock_timestamp() where id=$2")
        .bind(deletion)
        .bind(retired.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let app = routes(state(&e, &identity, e.authorization.clone()).await);
    let (status, result) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &format!("/organizations/{}/supervision", org.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{result}");
    let totals = &result["totals"];
    assert_eq!(totals["active"], json!({"documents":5,"bytes":5}));
    assert_eq!(totals["pending_purge"], json!({"documents":1,"bytes":1}));
    assert_eq!(totals["failed_documents"], 1);
    assert_eq!(
        totals["processing"],
        json!([{"status":"pending","stage":"queued","documents":1}])
    );
    assert_eq!(
        totals["published"],
        json!({
            "documents":4,"chunks":12,"vectors":12,"tabular_datasets":5,
            "known_rows":12,"datasets_with_unknown_rows":3,"total_rows":null
        })
    );
}
