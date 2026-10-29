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
async fn state(e: &Env, identity: &support::IdentityServer, fga: Fga) -> AppState {
    AppState {
        agent_catalog: Default::default(),
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
    json!({"name":name, "owner_username":owner, "admin_usernames":[admin]})
}

// Proves: I1, I5, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_console_creation_authority_roles_failures_and_budget() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    for user in [
        "owner",
        "admin",
        "both",
        "free-owner",
        "free-admin",
        "second",
    ] {
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
        (
            json!({"name":"B", "owner_username":"both", "admin_usernames":[]}),
            422,
        ),
        (
            json!({"name":"B", "owner_username":"both", "admin_usernames":vec!["both"; 51]}),
            422,
        ),
        (
            json!({"name":"B", "owner_username":"both", "admin_username":"both"}),
            422,
        ),
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
    // Several administrators, one of them the owner and one named twice: each distinct
    // nominee is checked once and every role lands in the single creation Write.
    *proxy.fault.lock().await = Default::default();
    let (status, both) = request(
        &app,
        &identity,
        Some("root"),
        "POST",
        "/admin/organizations",
        json!({"name":"B", "owner_username":"both", "admin_usernames":["both", "second", "second"]}),
    )
    .await;
    assert_eq!(status, 201, "{both}");
    {
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("check"), Some(&2));
        assert_eq!(fault.calls.get("read"), Some(&4));
        assert_eq!(fault.calls.get("write"), Some(&2));
        let roles_written = fault.written[1]["writes"]["tuple_keys"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|k| k["user"].as_str().is_some_and(|u| u.starts_with("user:")))
            .count();
        assert_eq!(roles_written, 3);
    }
    let both = Uuid::parse_str(both["id"].as_str().unwrap()).unwrap();
    let roles = e.fga.direct_roles_on("both", both).await.unwrap();
    assert_eq!(roles.len(), 2);
    assert!(roles.contains(&Role::OrganizationOwner));
    assert!(roles.contains(&Role::Admin));
    assert_eq!(
        e.fga.direct_roles_on("second", both).await.unwrap(),
        vec![Role::Admin]
    );
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
    sqlx::query("insert into deletion(id,target_id,target_kind,organization_id,actor_subject,requested_at,due_at) values($1,$2,'organization',$2,'root',now(),now())").bind(deletion).bind(retired).execute(&e.pool).await.unwrap();
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
            &["target".to_owned()],
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
    let admins = ["target".to_owned()];
    let (a, b) = tokio::join!(
        spaces::create_managed_organization(
            &e.pool, &e.fga, &resolver, "root", "One", "target", &admins
        ),
        spaces::create_managed_organization(
            &e.pool, &e.fga, &resolver, "root", "Two", "target", &admins
        )
    );
    assert_ne!(a.is_ok(), b.is_ok());
    assert!(matches!(a.err().or(b.err()), Some(AppError::Conflict(_))));
}

// Proves: I1, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_console_edit_replaces_name_owner_and_admin() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    for user in ["owner", "admin", "extra", "new-owner", "new-admin", "other"] {
        identity.users.lock().await.insert(user.into(), user.into());
    }
    bootstrap::grant_root(&e.pool, &e.fga, "root")
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
    let (_, org) = request(
        &app,
        &identity,
        Some("root"),
        "POST",
        "/admin/organizations",
        creation("A", "owner", "admin"),
    )
    .await;
    let id = Uuid::parse_str(org["id"].as_str().unwrap()).unwrap();
    request(
        &app,
        &identity,
        Some("root"),
        "POST",
        "/admin/organizations",
        creation("B", "other", "other"),
    )
    .await;
    let path = format!("/admin/organizations/{id}");
    let (status, detail) = request(&app, &identity, Some("root"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(detail["organization"]["name"], "A");
    assert_eq!(
        detail["owners"],
        json!([{"id":"owner","username":"owner","first_name":null,"last_name":null,"email":null,"avatar_image_url":null}])
    );
    assert_eq!(detail["admins"][0]["username"], "admin");
    for actor in [None, Some("owner")] {
        for method in ["GET", "PATCH"] {
            assert_eq!(
                request(&app, &identity, actor, method, &path, json!({"name":"X"}))
                    .await
                    .0,
                if actor.is_none() { 401 } else { 403 }
            );
        }
    }
    let missing = format!("/admin/organizations/{}", Uuid::new_v4());
    for (path, body, expected) in [
        (&missing, json!({"name":"X"}), 404),
        (&path, json!({}), 422),
        (&path, json!({"name":" "}), 422),
        (&path, json!({"name":"B"}), 409),
        (&path, json!({"owner_username":"missing"}), 422),
        (&path, json!({"admin_usernames":["missing"]}), 422),
        (&path, json!({"admin_usernames":["admin", "other"]}), 409),
        (&path, json!({"admin_usernames":[]}), 422),
        (&path, json!({"admin_username":"admin"}), 422),
        (&path, json!({"owner":"x"}), 422),
    ] {
        assert_eq!(
            request(&app, &identity, Some("root"), "PATCH", path, body.clone())
                .await
                .0,
            expected,
            "{body}"
        );
    }
    // A failed publication changes neither the row nor the roles.
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        fail_at: 1,
        ..Default::default()
    };
    let rename =
        json!({"name":"A2", "owner_username":"new-owner", "admin_usernames":["new-admin"]});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("root"),
            "PATCH",
            &path,
            rename.clone()
        )
        .await
        .0,
        500
    );
    assert!(
        db::organization_named(&e.pool, "A2")
            .await
            .unwrap()
            .is_none()
    );
    assert_eq!(
        e.fga.direct_roles_on("owner", id).await.unwrap(),
        vec![Role::OrganizationOwner]
    );
    // An administrator appointed inside the organization is replaced too.
    spaces::grant(
        &e.pool,
        &e.fga,
        &control_plane::users::Directory::Keycloak(Some(&identity.directory())),
        "owner",
        id,
        Role::Admin,
        "extra",
    )
    .await
    .unwrap();
    *proxy.fault.lock().await = Default::default();
    let (status, detail) = request(
        &app,
        &identity,
        Some("root"),
        "PATCH",
        &path,
        rename.clone(),
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(detail["organization"]["name"], "A2");
    assert_eq!(detail["owners"][0]["username"], "new-owner");
    assert_eq!(detail["admins"].as_array().unwrap().len(), 1);
    assert_eq!(detail["admins"][0]["username"], "new-admin");
    // Two owner Checks; guard, holder and attachment Reads, none after commit; one Write.
    assert_eq!(
        proxy.fault.lock().await.calls,
        [("check", 2), ("read", 6), ("write", 1)]
            .map(|(k, v)| (k.to_owned(), v))
            .into_iter()
            .collect()
    );
    for who in ["owner", "admin", "extra"] {
        assert!(e.fga.direct_roles_on(who, id).await.unwrap().is_empty());
        assert!(
            spaces::organization(&e.pool, &e.fga, who)
                .await
                .unwrap()
                .is_none()
        );
    }
    assert_eq!(
        e.fga.direct_roles_on("new-admin", id).await.unwrap(),
        vec![Role::Admin]
    );
    for who in ["root", "new-owner", "new-admin"] {
        assert!(!reads(&e, who, id).await);
    }
    // Replay is idempotent, and an unchanged name is not a conflict with itself.
    *proxy.fault.lock().await = Default::default();
    assert_eq!(
        request(&app, &identity, Some("root"), "PATCH", &path, rename)
            .await
            .0,
        200
    );
    assert!(
        !proxy
            .fault
            .lock()
            .await
            .written
            .iter()
            .any(|w| w.to_string().contains("user:"))
    );
    assert!(
        db::organization_named(&e.pool, "A")
            .await
            .unwrap()
            .is_none()
    );
    // A directory failure after commit degrades to id-only summaries, never an error.
    identity
        .users
        .lock()
        .await
        .insert("unavailable".into(), "flaky".into());
    let (status, detail) = request(
        &app,
        &identity,
        Some("root"),
        "PATCH",
        &path,
        json!({"owner_username":"flaky"}),
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(
        detail["owners"],
        json!([{"id":"unavailable","username":null,"first_name":null,"last_name":null,"email":null,"avatar_image_url":null}])
    );
    assert_eq!(detail["admins"][0]["username"], "new-admin");
    assert_eq!(
        e.fga.direct_roles_on("unavailable", id).await.unwrap(),
        vec![Role::OrganizationOwner]
    );
    // The administrator list is the desired set: only the difference is written.
    *proxy.fault.lock().await = Default::default();
    let (status, detail) = request(
        &app,
        &identity,
        Some("root"),
        "PATCH",
        &path,
        json!({"admin_usernames":["new-admin", "extra"]}),
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(detail["admins"].as_array().unwrap().len(), 2);
    let written = proxy.fault.lock().await.written.clone();
    assert_eq!(written.len(), 1, "{written:?}");
    assert!(written[0].to_string().contains("user:extra"));
    assert!(!written[0].to_string().contains("user:new-admin"));
    let (status, detail) = request(
        &app,
        &identity,
        Some("root"),
        "PATCH",
        &path,
        json!({"admin_usernames":["extra"]}),
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(detail["admins"][0]["username"], "extra");
    assert!(
        e.fga
            .direct_roles_on("new-admin", id)
            .await
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        e.fga.direct_roles_on("extra", id).await.unwrap(),
        vec![Role::Admin]
    );
    // The new owner may be named among the administrators too.
    let (status, detail) = request(
        &app,
        &identity,
        Some("root"),
        "PATCH",
        &path,
        json!({"owner_username":"extra", "admin_usernames":["extra"]}),
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    let roles = e.fga.direct_roles_on("extra", id).await.unwrap();
    assert_eq!(roles.len(), 2);
    assert!(roles.contains(&Role::OrganizationOwner));
    assert!(
        e.fga
            .direct_roles_on("unavailable", id)
            .await
            .unwrap()
            .is_empty()
    );
    // A delta beyond one guarded Write is refused before publication, not failed by it.
    let batch = |prefix: &str| -> Vec<String> { (0..50).map(|i| format!("{prefix}{i}")).collect() };
    for user in batch("p").into_iter().chain(batch("q")) {
        identity.users.lock().await.insert(user.clone(), user);
    }
    let fifty = json!({"admin_usernames": batch("p")});
    assert_eq!(
        request(&app, &identity, Some("root"), "PATCH", &path, fifty)
            .await
            .0,
        200
    );
    let others = json!({"admin_usernames": batch("q")});
    assert_eq!(
        request(&app, &identity, Some("root"), "PATCH", &path, others)
            .await
            .0,
        422
    );
    assert_eq!(
        e.fga.space_holders(id, Role::Admin).await.unwrap().len(),
        50
    );
    assert!(e.fga.direct_roles_on("q0", id).await.unwrap().is_empty());
}

// Proves: I1, I5, I23. Owner-only HTTP access, isolated totals and direct grants.
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn supervision_isolates_organizations_and_drains_role_pages() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let other = support::member_organization(&e.pool, &e.fga, "O2", "bob")
        .await
        .unwrap();
    let project = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "alice",
    )
    .await
    .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "alice", org.id)
        .await
        .unwrap();
    for space in [org.id, team.id, project.id, personal.id, other.id] {
        environment::insert_document(&e.pool, &document(space, None, "one.txt"))
            .await
            .unwrap();
    }
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
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
    let app = routes(state(&e, &identity, observed).await);
    let path = format!("/organizations/{}/supervision", org.id);
    for (actor, expected) in [
        (None, 401),
        (Some("alice"), 403),
        (Some("root"), 404),
        (Some("bob-owner"), 404),
    ] {
        assert_eq!(
            request(&app, &identity, actor, "GET", &path, Value::Null)
                .await
                .0,
            expected
        );
    }
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        read_page_size: Some(1),
        ..Default::default()
    };
    let (status, result) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{result}");
    assert_eq!(result["active_teams"], 1);
    assert_eq!(result["totals"]["active"]["documents"], 4);
    assert_eq!(result["organization_direct"]["active"]["documents"], 1);
    assert_eq!(result["teams_total"]["active"]["documents"], 2);
    assert_eq!(result["personal_total"]["active"]["documents"], 1);
    assert_eq!(result["totals"]["distinct_users"], 2);
    assert_eq!(result["teams_total"]["distinct_users"], 1);
    assert_eq!(result["totals"]["published"]["total_rows"], 0);
    assert!(!result.to_string().contains("alice"));
    let roles = result["totals"]["direct_roles"].as_array().unwrap();
    assert!(
        roles
            .iter()
            .any(|r| r["role"] == "admin" && r["assignments"] == 3)
    );
    let fault = proxy.fault.lock().await;
    assert!(fault.reads.iter().any(|r| r["continuation_token"] != ""));
    assert_eq!(fault.calls.get("check"), Some(&1));
    assert!(!fault.calls.contains_key("write"));
    assert!(fault.peak_reads <= 8);
    drop(fault);
    let detail = format!("{path}/teams/{}", team.id);
    let (status, result) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &detail,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{result}");
    assert_eq!(result["team"]["counts"]["active"]["documents"], 2);
    for id in [other.id, personal.id, project.id] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice-owner"),
                "GET",
                &format!("{path}/teams/{id}"),
                Value::Null
            )
            .await
            .0,
            404
        );
    }
    let (status, result) = request(
        &app,
        &identity,
        Some("bob-owner"),
        "GET",
        &format!("/organizations/{}/supervision", other.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{result}");
    assert_eq!(result["active_teams"], 0);
    assert_eq!(result["totals"]["active"]["documents"], 1);
    assert_eq!(result["teams"]["items"], json!([]));
    // The first Read is actor context; fail after the successful owner Check.
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        fail_read_at: 2,
        ..Default::default()
    };
    let (status, error) = request(
        &app,
        &identity,
        Some("alice-owner"),
        "GET",
        &path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 503, "{error}");
    assert_eq!(error["code"], "dependency_unavailable");
    assert!(error.get("totals").is_none());
    assert!(!error.to_string().contains("private-dependency-error"));
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
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
    let app = routes(state(&e, &identity, e.fga.clone()).await);
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
        expires_at,prefix,committed_at,chunks,vector_ordinals,rows,cleanup_after)
        values($1,$2,'indexing',$1,$1,1,now(),'fixture/',now(),7,'{0,1,2}',$3,now())",
    )
    .bind(generation)
    .bind(id)
    .bind(rows)
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
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
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
    let app = routes(state(&e, &identity, e.fga.clone()).await);
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
