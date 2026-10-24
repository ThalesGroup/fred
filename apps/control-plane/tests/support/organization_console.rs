// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use axum::{
    body::{Body, to_bytes},
    http::Request,
};
use control_plane::{
    api::{AppState, routes},
    onboarding::Onboarding,
};
use serde_json::{Value, json};
use std::sync::Arc;
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
async fn state(e: &Env, identity: &support::IdentityServer, fga: Fga) -> AppState {
    AppState {
        pool: e.pool.clone(),
        fga,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    }
}
fn creation(name: &str, owner: &str, admin: &str) -> Value {
    json!({"name":name, "owner_username":owner, "admin_username":admin})
}

// Proves: I1, I5, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_console_creation_authority_roles_failures_and_budget() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    for user in ["owner", "admin", "both", "free-owner", "free-admin"] {
        identity.users.lock().await.insert(user.into(), user.into());
    }
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let observed = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let state = state(&e, &identity, observed).await;
    let app = routes(state.clone());
    for actor in [None, Some("ordinary")] {
        assert_eq!(
            request(
                &app,
                &identity,
                actor,
                "POST",
                "/admin/organizations",
                creation("A", "owner", "admin")
            )
            .await
            .0,
            if actor.is_none() { 401 } else { 403 }
        );
        assert_eq!(
            request(
                &app,
                &identity,
                actor,
                "GET",
                "/admin/organizations",
                Value::Null
            )
            .await
            .0,
            if actor.is_none() { 401 } else { 403 }
        );
    }
    let guarded = routes(AppState {
        onboarding: Onboarding {
            gcu_version: Some("v1".into()),
            ..Default::default()
        },
        ..state
    });
    assert_eq!(
        request(
            &guarded,
            &identity,
            Some("root"),
            "POST",
            "/admin/organizations",
            creation("A", "owner", "admin")
        )
        .await
        .0,
        403
    );
    *proxy.fault.lock().await = Default::default();
    let (status, org) = request(
        &app,
        &identity,
        Some("root"),
        "POST",
        "/admin/organizations",
        creation("A", "owner", "admin"),
    )
    .await;
    assert_eq!(status, 201, "{org}");
    let calls = proxy.fault.lock().await.calls.clone();
    assert_eq!(calls.get("check"), Some(&2));
    assert_eq!(calls.get("read"), Some(&4));
    assert_eq!(calls.get("write"), Some(&2));
    assert!(!calls.contains_key("list-objects"));
    let id = Uuid::parse_str(org["id"].as_str().unwrap()).unwrap();
    assert_eq!(
        e.fga.direct_roles_on("owner", id).await.unwrap(),
        vec![Role::OrganizationOwner]
    );
    assert_eq!(
        e.fga.direct_roles_on("admin", id).await.unwrap(),
        vec![Role::Admin]
    );
    for who in ["root", "owner", "admin"] {
        assert!(!reads(&e, who, id).await);
    }
    assert!(
        spaces::memberships(&e.pool, &e.fga, "root")
            .await
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("owner"),
            "GET",
            "/admin/organizations",
            Value::Null
        )
        .await
        .0,
        403
    );
    for (body, expected) in [
        (creation("A", "both", "both"), 409),
        (creation("B", "owner", "both"), 409),
        (creation("B", "missing", "both"), 422),
        (creation("B", "both", "missing"), 422),
        (creation(" ", "both", "both"), 422),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("root"),
                "POST",
                "/admin/organizations",
                body
            )
            .await
            .0,
            expected
        );
    }
    let (status, both) = request(
        &app,
        &identity,
        Some("root"),
        "POST",
        "/admin/organizations",
        creation("B", "both", "both"),
    )
    .await;
    assert_eq!(status, 201, "{both}");
    let roles = e
        .fga
        .direct_roles_on(
            "both",
            Uuid::parse_str(both["id"].as_str().unwrap()).unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(roles.len(), 2);
    assert!(roles.contains(&Role::OrganizationOwner));
    assert!(roles.contains(&Role::Admin));
    for after in [false, true] {
        *proxy.fault.lock().await = support::fga_proxy::Fault {
            fail_at: 2,
            after,
            ..Default::default()
        };
        assert_eq!(
            request(
                &app,
                &identity,
                Some("root"),
                "POST",
                "/admin/organizations",
                creation("Failed", "free-owner", "free-admin")
            )
            .await
            .0,
            500
        );
        assert!(
            db::organization_named(&e.pool, "Failed")
                .await
                .unwrap()
                .is_none()
        );
        assert!(
            spaces::organization(&e.pool, &e.fga, "free-owner")
                .await
                .unwrap()
                .is_none()
        );
    }
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_console_registry_pagination_excludes_retired_and_costs_one_check() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let mut ids = Vec::new();
    for index in 0..102 {
        let id = Uuid::new_v4();
        ids.push(id);
        sqlx::query(
            "insert into space(id,kind,name,organization_id) values($1,'organization',$2,$1)",
        )
        .bind(id)
        .bind(format!("Org {index}"))
        .execute(&e.pool)
        .await
        .unwrap();
    }
    let retired = ids.pop().unwrap();
    let deletion = Uuid::new_v4();
    sqlx::query("insert into space_deletion(id,target_id,target_kind,organization_id,actor_subject,requested_at,due_at) values($1,$2,'organization',$2,'root',now(),now())").bind(deletion).bind(retired).execute(&e.pool).await.unwrap();
    sqlx::query("update space set deletion_id=$1 where id=$2")
        .bind(deletion)
        .bind(retired)
        .execute(&e.pool)
        .await
        .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let observed = Fga::connect(&proxy.base, &e.store, false, false, None, None)
        .await
        .unwrap()
        .load(&e.pool)
        .await
        .unwrap();
    let app = routes(state(&e, &identity, observed).await);
    *proxy.fault.lock().await = Default::default();
    let (status, page) = request(
        &app,
        &identity,
        Some("root"),
        "GET",
        "/admin/organizations",
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(page["items"].as_array().unwrap().len(), 100);
    assert_eq!(
        proxy.fault.lock().await.calls,
        [("check".to_owned(), 1)].into_iter().collect()
    );
    let (_, last) = request(
        &app,
        &identity,
        Some("root"),
        "GET",
        &format!(
            "/admin/organizations?after={}",
            page["next_cursor"].as_str().unwrap()
        ),
        Value::Null,
    )
    .await;
    assert_eq!(last["items"].as_array().unwrap().len(), 1);
    assert!(last["next_cursor"].is_null());
    let mut actual: Vec<_> = page["items"]
        .as_array()
        .unwrap()
        .iter()
        .chain(last["items"].as_array().unwrap())
        .map(|row| Uuid::parse_str(row["id"].as_str().unwrap()).unwrap())
        .collect();
    actual.sort();
    ids.sort();
    assert_eq!(actual, ids);
}

// Proves: I5, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_console_rechecks_waiting_creator_and_serializes_attachment() {
    use control_plane::roles::PlatformRole;
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    identity
        .users
        .lock()
        .await
        .insert("target".into(), "target".into());
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform(
            &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
            "delegate",
            PlatformRole::PlatformOwner,
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
    let (pool, fga, directory) = (e.pool.clone(), e.fga.clone(), identity.directory());
    let pending = tokio::spawn(async move {
        spaces::create_managed_organization(
            &pool,
            &fga,
            &control_plane::users::Directory::Keycloak(Some(&directory)),
            "delegate",
            "Revoked",
            "target",
            "target",
        )
        .await
    });
    wait_for_advisory_waiter(&e.pool).await;
    delete_tuple(&e, "delegate", "platform_owner", "platform:root").await;
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
            &e.pool, &e.fga, &resolver, "root", "One", "target", "target"
        ),
        spaces::create_managed_organization(
            &e.pool, &e.fga, &resolver, "root", "Two", "target", "target"
        )
    );
    assert_ne!(a.is_ok(), b.is_ok());
    assert!(matches!(a.err().or(b.err()), Some(AppError::Conflict(_))));
}
