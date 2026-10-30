// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    body::{Body, to_bytes},
    http::Request,
};
use serde_json::Value;
use tower::ServiceExt;

async fn get(app: &axum::Router, token: &str, path: &str) -> (u16, Value) {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .uri(path)
                .header("authorization", format!("Bearer {token}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status().as_u16();
    let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    (
        status,
        serde_json::from_slice(&body)
            .unwrap_or_else(|_| Value::String(String::from_utf8_lossy(&body).into_owned())),
    )
}

// Proves: I1, I6, I8, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn resource_reads_enforce_scope_and_role_semantics() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    let (org, team) = org_and_team(&e).await;
    for (user, role) in [
        ("reader", Role::Member),
        ("editor", Role::Editor),
        ("analyst", Role::Analyst),
        ("admin", Role::Admin),
    ] {
        grant(&e, org.id, Role::Member, user).await;
        grant(&e, team.id, role, user).await;
    }
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "reader", org.id)
        .await
        .unwrap()
        .0;
    let folder = |space_id, name: &str, parent: Option<&Folder>| {
        let id = Uuid::new_v4();
        Folder {
            created_at: chrono::Utc::now(),
            id,
            space_id,
            name: name.into(),
            parent_id: parent.map(|f| f.id),
            path: domain::folder_path(parent, id),
        }
    };
    let root = folder(team.id, "Library", None);
    let child = folder(team.id, "Empty", Some(&root));
    let private = folder(personal.id, "Private", None);
    for f in [&root, &child, &private] {
        db::insert_folder(&e.pool, f).await.unwrap();
    }
    let mut expected = vec![child.id];
    for i in 0..53 {
        let d = Document {
            retrievable: false,
            retrievable_pending: false,
            id: Uuid::new_v4(),
            space_id: team.id,
            folder_id: Some(root.id),
            name: format!("document-{:02}.txt", i),
            mime: "text/plain".into(),
            size: 1,
            sha256: format!("{i:064x}"),
            created_by: "editor".into(),
            created_at: chrono::Utc::now(),
        };
        crate::environment::insert_document(&e.pool, &d)
            .await
            .unwrap();
        expected.push(d.id);
    }
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
    let app = control_plane::api::routes(control_plane::api::AppState {
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: std::sync::Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        fga: observed,
        directory: None,
        content: None,
        processing: None,
    });
    let reader = identity.token("reader");
    let base = format!("/spaces/{}", team.id);
    let (status, body) = get(&app, &reader, &format!("{base}/entries")).await;
    assert_eq!(status, 200, "{body}");
    assert_eq!(body["items"].as_array().unwrap().len(), 1);
    let docs = format!("{base}/entries?parent_id={}&limit=50", root.id);
    let (status, first) = get(&app, &reader, &docs).await;
    assert_eq!(status, 200);
    assert_eq!(first["total"], 54);
    let (_, second) = get(&app, &reader, &format!("{docs}&offset=50")).await;
    // Folders come first, then documents by name; two pages cover the directory once.
    let ids: Vec<String> = [&first, &second]
        .iter()
        .flat_map(|page| page["items"].as_array().unwrap().iter())
        .map(|item| item["data"]["id"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(first["items"].as_array().unwrap().len(), 50);
    assert_eq!(second["items"].as_array().unwrap().len(), 4);
    assert_eq!(
        ids,
        expected.iter().map(Uuid::to_string).collect::<Vec<_>>()
    );
    for invalid in [private.id, Uuid::new_v4()] {
        assert_eq!(
            get(
                &app,
                &reader,
                &format!("{base}/entries?parent_id={invalid}")
            )
            .await
            .0,
            404
        );
    }
    let (status, body) = get(
        &app,
        &reader,
        &format!("{base}/entries?parent_id={}", child.id),
    )
    .await;
    assert_eq!(status, 200);
    assert!(body["items"].as_array().unwrap().is_empty());
    for user in ["reader", "editor", "analyst"] {
        assert_eq!(
            get(&app, &identity.token(user), &format!("{base}/entries"))
                .await
                .0,
            200
        );
    }
    assert_eq!(
        get(&app, &identity.token("admin"), &format!("{base}/entries"))
            .await
            .0,
        403
    );
    assert_eq!(
        get(
            &app,
            &identity.token("alice"),
            &format!("/spaces/{}/entries", personal.id)
        )
        .await
        .0,
        403
    );
    // Same read budget with 0 or 53 documents, concurrency 1. Force role paging.
    for path in [format!("{base}/entries"), docs.clone()] {
        *proxy.fault.lock().await = support::fga_proxy::Fault {
            read_page_size: Some(1),
            ..Default::default()
        };
        assert_eq!(get(&app, &reader, &path).await.0, 200);
        let fault = proxy.fault.lock().await;
        // Read decision plus the directory's current write decision.
        assert_eq!(fault.calls.get("check"), Some(&2));
        assert_eq!(fault.writes, 0);
        assert_eq!(fault.calls.len(), 2);
        // Five direct-role pages, zero placement Reads for context or target.
        assert_eq!(fault.calls.get("read"), Some(&5));
        assert!(fault.reads.iter().any(|r| {
            r["continuation_token"]
                .as_str()
                .is_some_and(|s| !s.is_empty())
        }));
    }
    spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "reader")
        .await
        .unwrap();
    assert_eq!(get(&app, &reader, &docs).await.0, 403);
    assert_eq!(get(&app, &reader, &format!("{base}/entries")).await.0, 403);
    let other = crate::support::member_organization(&e.pool, &e.fga, "Other", "outsider")
        .await
        .unwrap();
    assert_eq!(
        get(&app, &reader, &format!("/spaces/{}/entries", other.id))
            .await
            .0,
        404
    );
}

// Proves: I1, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn sql_placement_matches_fga_hierarchy_and_context() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Analyst, "reader").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "reader", org.id)
        .await
        .unwrap();

    // Independent reference: the previous resolver followed FGA links, not SQL placement.
    for expected in [&org, &team, &project, &personal] {
        let mut ancestors = Vec::new();
        let organization = if expected.personal_owner.is_some() {
            e.fga.link_of(expected.id, true).await.unwrap().unwrap()
        } else {
            if expected.kind != SpaceKind::Organization {
                let parent = e.fga.link_of(expected.id, false).await.unwrap().unwrap();
                ancestors.push(parent);
                if expected.kind == SpaceKind::Project {
                    ancestors.insert(0, e.fga.link_of(parent, false).await.unwrap().unwrap());
                }
            }
            ancestors.first().copied().unwrap_or(expected.id)
        };
        let parent = ancestors.last().copied();
        ancestors.push(expected.id);
        let actual = spaces::load(&e.pool, expected.id).await.unwrap();
        assert_eq!(
            (actual.organization, actual.parent_id, actual.path),
            (organization, parent, ancestors)
        );
    }
    for user in ["alice", "reader", "unattached"] {
        let roles = e.fga.roles_of(user).await.unwrap();
        let ids: Vec<_> = roles.iter().map(|(id, _)| *id).collect();
        let mut organizations = std::collections::BTreeSet::new();
        for row in db::spaces(&e.pool, &ids).await.unwrap() {
            let organization = if row.personal_owner.is_some() {
                e.fga.link_of(row.id, true).await.unwrap().unwrap()
            } else if row.kind == SpaceKind::Organization {
                row.id
            } else {
                let parent = e.fga.link_of(row.id, false).await.unwrap().unwrap();
                if row.kind == SpaceKind::Project {
                    e.fga.link_of(parent, false).await.unwrap().unwrap()
                } else {
                    parent
                }
            };
            organizations.insert(organization);
        }
        assert!(organizations.len() <= 1);
        assert_eq!(
            spaces::organization(&e.pool, &e.fga, user).await.unwrap(),
            organizations.first().copied()
        );
    }
    let memberships = spaces::memberships(&e.pool, &e.fga, "reader")
        .await
        .unwrap();
    assert_eq!(memberships.len(), 4);
    for membership in memberships {
        let expected = [&org, &team, &project, &personal]
            .into_iter()
            .find(|s| s.id == membership.space.id)
            .unwrap();
        assert_eq!(membership.space.path, expected.path);
        assert_eq!(membership.space.organization, org.id);
    }
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_context_reads_only_role_pages() {
    let e = env().await;
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    grant(&e, org.id, Role::Member, "reader").await;
    // Distinct teams must not add any placement RPC to context resolution.
    for i in 0..40 {
        let team = spaces::create_space(
            &e.pool,
            &e.fga,
            "alice",
            SpaceKind::Team,
            org.id,
            format!("Team {i}"),
            "alice",
        )
        .await
        .unwrap();
        grant(&e, team.id, Role::Member, "reader").await;
    }
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
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        read_page_size: Some(10),
        ..Default::default()
    };
    assert_eq!(
        spaces::organization(&e.pool, &observed, "reader")
            .await
            .unwrap(),
        Some(org.id)
    );
    let fault = proxy.fault.lock().await;
    assert_eq!(fault.calls.get("read"), Some(&5)); // five role pages, no links
    assert_eq!(fault.calls.len(), 1);
    assert_eq!(fault.writes, 0);
    assert!(fault.reads.iter().all(|r| {
        r["tuple_key"]["user"] == "user:reader"
            && r["tuple_key"]["object"] == "space:"
            && r["tuple_key"].get("relation").is_none()
            && r["consistency"] == "HIGHER_CONSISTENCY"
    }));
    assert_eq!(fault.active_reads, 0);
}

async fn create(
    app: &axum::Router,
    token: &str,
    space: Uuid,
    parent: Option<Uuid>,
    name: &str,
) -> (u16, Value) {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/folders")
                .header("authorization", format!("Bearer {token}"))
                .header("content-type", "application/json")
                .body(Body::from(
                    serde_json::json!({"space_id":space,"parent_id":parent,"name":name})
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status().as_u16();
    let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    (
        status,
        serde_json::from_slice(&body)
            .unwrap_or_else(|_| Value::String(String::from_utf8_lossy(&body).into_owned())),
    )
}

// Proves: I1, I2, I5, I6, I8, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn folder_creation_governance_contract_and_request_budget() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    let (org, team) = org_and_team(&e).await;
    for (user, role) in [
        ("writer", Role::Editor),
        ("reader", Role::Member),
        ("analyst", Role::Analyst),
        ("admin", Role::Admin),
    ] {
        grant(&e, org.id, Role::Member, user).await;
        grant(&e, team.id, role, user).await;
    }
    grant(&e, org.id, Role::Editor, "inherited").await;
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "writer", org.id)
        .await
        .unwrap()
        .0;
    let other = crate::support::member_organization(&e.pool, &e.fga, "Other", "outsider")
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
    let app = control_plane::api::routes(control_plane::api::AppState {
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: std::sync::Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        fga: observed,
        directory: None,
        content: None,
        processing: None,
    });
    let token = identity.token("writer");
    let (status, root) = create(&app, &token, team.id, None, "  Dossiers été  ").await;
    assert_eq!(status, 201, "{root}");
    assert_eq!(root["name"], "Dossiers été");
    let root_id = Uuid::parse_str(root["id"].as_str().unwrap()).unwrap();
    let (status, child) = create(&app, &token, team.id, Some(root_id), "child").await;
    assert_eq!(status, 201, "{child}");
    assert_eq!(child["parent_id"], root["id"]);
    assert_eq!(
        create(&app, &token, team.id, None, "Dossiers été").await.0,
        409
    );
    assert_eq!(
        create(&app, &token, team.id, Some(root_id), "Dossiers été")
            .await
            .0,
        201
    );
    assert_eq!(
        create(&app, &token, team.id, Some(Uuid::new_v4()), "missing")
            .await
            .0,
        404
    );
    let (status, private) = create(&app, &token, personal.id, None, "private").await;
    assert_eq!(status, 201);
    let private_id = Uuid::parse_str(private["id"].as_str().unwrap()).unwrap();
    assert_eq!(
        create(&app, &token, team.id, Some(private_id), "foreign")
            .await
            .0,
        400
    );
    for name in ["", "   ", "a/b", "a\\b", "x\0y", "x\ny", &"é".repeat(256)] {
        assert_eq!(
            create(&app, &token, team.id, None, name).await.0,
            422,
            "{name:?}"
        );
    }
    assert_eq!(
        create(&app, &token, team.id, None, &"🦀".repeat(255))
            .await
            .0,
        201
    );
    let mut parent = root_id;
    for depth in 2..=15 {
        let (status, folder) = create(
            &app,
            &token,
            team.id,
            Some(parent),
            &format!("depth-{depth}"),
        )
        .await;
        assert_eq!(status, 201, "{folder}");
        parent = Uuid::parse_str(folder["id"].as_str().unwrap()).unwrap();
    }
    assert_eq!(
        create(&app, &token, team.id, Some(parent), "too-deep")
            .await
            .0,
        422
    );
    // Same organization without write: 403; outside the organization: 404.
    for (user, status) in [
        ("reader", 403),
        ("analyst", 403),
        ("admin", 403),
        ("alice", 403),
        ("outsider", 404),
    ] {
        assert_eq!(
            create(&app, &identity.token(user), team.id, None, "forbidden")
                .await
                .0,
            status,
            "{user}"
        );
    }
    assert_eq!(
        create(&app, &token, other.id, None, "foreign-org").await.0,
        404
    );
    assert_eq!(
        create(
            &app,
            &identity.token("inherited"),
            personal.id,
            None,
            "private"
        )
        .await
        .0,
        403
    );
    assert_eq!(
        create(
            &app,
            &identity.token("inherited"),
            team.id,
            None,
            "inherited"
        )
        .await
        .0,
        201
    );
    // One inherited org-editor tuple, one HTTP request at a time, one tuple/page.
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        read_page_size: Some(1),
        ..Default::default()
    };
    let started = std::time::Instant::now();
    assert_eq!(
        create(&app, &identity.token("inherited"), team.id, None, "budget")
            .await
            .0,
        201
    );
    let fault = proxy.fault.lock().await;
    assert_eq!(fault.calls.get("read"), Some(&2));
    assert_eq!(fault.calls.get("check"), Some(&1));
    assert_eq!(fault.calls.get("write"), Some(&1));
    assert_eq!(fault.calls.len(), 3);
    assert_eq!(
        fault.written[0]["writes"]["tuple_keys"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        fault.written[0]["deletes"]["tuple_keys"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(
        fault.written[0]["writes"]["tuple_keys"][0]["object"]
            .as_str()
            .unwrap()
            .starts_with("guard:")
    );
    eprintln!(
        "folder create: 1 org-editor tuple, HTTP concurrency 1, 3 Reads/1 Check/1 Write; elapsed {:?}",
        started.elapsed()
    );
    drop(fault);
    let (a, b) = tokio::join!(
        create(&app, &token, team.id, None, "concurrent"),
        create(&app, &token, team.id, None, "concurrent")
    );
    assert!(matches!((a.0, b.0), (201, 409) | (409, 201)));
    let held = hold_organization_lock(&e, org.id).await;
    let since = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let waiting_app = app.clone();
    let waiting_token = token.clone();
    let waiting = tokio::spawn(async move {
        create(
            &waiting_app,
            &waiting_token,
            team.id,
            None,
            "revoked-waiter",
        )
        .await
    });
    wait_for_write_retry(&e.pool, since).await;
    delete_tuple(&e, "writer", "editor", &format!("space:{}", team.id)).await;
    held.commit().await.unwrap();
    assert_eq!(waiting.await.unwrap().0, 403);
    assert_eq!(create(&app, &token, team.id, None, "revoked").await.0, 403);
    let count:i64 = sqlx::query_scalar("select count(*) from folder where name in ('forbidden','foreign','foreign-org','revoked','revoked-waiter','too-deep')").fetch_one(&e.pool).await.unwrap();
    assert_eq!(count, 0);
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn folder_rename_preserves_creation_name_rules() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let folder = spaces::create_folder(&e.pool, &e.fga, "alice", org.id, None, "Original".into())
        .await
        .unwrap();
    let path = format!("/folders/{}", folder.id);
    for name in [
        "".into(),
        "  ".into(),
        "a/b".into(),
        "a\\b".into(),
        "a\nb".into(),
        "é".repeat(256),
    ] {
        let body = serde_json::json!({"name":name}).to_string();
        assert_eq!(
            content_request(app.clone(), &identity.token("alice"), "PATCH", &path, &body).await,
            422
        );
        assert_eq!(
            db::folder(&e.pool, folder.id).await.unwrap().name,
            "Original"
        );
    }
    let name = "é".repeat(255);
    assert_eq!(
        content_request(
            app,
            &identity.token("alice"),
            "PATCH",
            &path,
            &serde_json::json!({"name":format!("  {name}  ")}).to_string()
        )
        .await,
        204
    );
    let renamed = db::folder(&e.pool, folder.id).await.unwrap();
    assert_eq!(renamed.name, name);
    assert_eq!(renamed.path, folder.path);
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn space_names_match_organization_and_child_http_creation_contracts() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    for name in ["".into(), "  ".into(), "a\nb".into(), "é".repeat(181)] {
        assert!(matches!(
            crate::support::member_organization(&e.pool, &e.fga, &name, "bob").await,
            Err((422, _))
        ));
        for (kind, parent) in [("team", org.id), ("project", team.id)] {
            let body =
                serde_json::json!({"kind":kind,"parent_id":parent,"name":name,"admin":"alice"})
                    .to_string();
            assert_eq!(
                content_request(
                    app.clone(),
                    &identity.token("alice"),
                    "POST",
                    "/spaces",
                    &body
                )
                .await,
                422
            );
        }
    }
    assert!(e.fga.roles_of("bob").await.unwrap().is_empty());
    let name = format!(" /{} ", "é".repeat(177));
    let other = crate::support::member_organization(&e.pool, &e.fga, &name, "bob")
        .await
        .unwrap();
    // Inner spaces and slashes are kept; surrounding whitespace is not.
    assert_eq!(other.name, name.trim());
    let body = serde_json::json!({"kind":"team","parent_id":org.id,"name":name,"admin":"alice"})
        .to_string();
    assert_eq!(
        content_request(app, &identity.token("alice"), "POST", "/spaces", &body).await,
        201
    );
}

// Proves: I2
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn folder_directory_pages_and_atomic_subtree_lifecycle() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    grant(&e, org.id, Role::Member, "reader").await;
    grant(&e, team.id, Role::Member, "reader").await;
    let app = content_app(&e, &identity).await;
    let token = identity.token("writer");
    let root = spaces::create_folder(&e.pool, &e.fga, "writer", team.id, None, "root".into())
        .await
        .unwrap();
    let child = spaces::create_folder(
        &e.pool,
        &e.fga,
        "writer",
        team.id,
        Some(root.id),
        "child".into(),
    )
    .await
    .unwrap();
    let grandchild = spaces::create_folder(
        &e.pool,
        &e.fga,
        "writer",
        team.id,
        Some(child.id),
        "leaf".into(),
    )
    .await
    .unwrap();
    sqlx::query(
        "insert into folder (id, space_id, parent_id, name, path, created_at)
        select id, $1, $2, 'entry-' || lpad(n::text, 4, '0'), $3 || id || '/',
            '2026-01-01'::timestamptz + n * interval '1 second'
        from (select n, gen_random_uuid() id from generate_series(1, 230) n) seeded",
    )
    .bind(team.id)
    .bind(root.id)
    .bind(&root.path)
    .execute(&e.pool)
    .await
    .unwrap();
    let url = format!(
        "/control-plane/v1/spaces/{}/entries?parent_id={}",
        team.id, root.id
    );
    let (status, first) = get(&app, &token, &url).await;
    assert_eq!(status, 200, "{first}");
    assert_eq!(first["items"].as_array().unwrap().len(), 50);
    assert_eq!(first["total"], 231);
    assert_eq!(first["can_write"], true);
    assert_eq!(first["ancestors"][0]["id"], root.id.to_string());
    assert_eq!(
        first["items"][0]["data"]["created_at"],
        serde_json::to_value(child.created_at).unwrap()
    );
    assert_eq!(
        get(&app, &identity.token("reader"), &url).await.1["can_write"],
        false
    );
    let (_, last) = get(&app, &token, &format!("{url}&offset=200&limit=200")).await;
    assert_eq!(last["items"].as_array().unwrap().len(), 31);
    let (_, capped) = get(&app, &token, &format!("{url}&limit=99999")).await;
    assert_eq!(capped["items"].as_array().unwrap().len(), 200);
    let (_, past_end) = get(&app, &token, &format!("{url}&offset=99999")).await;
    assert_eq!(past_end["total"], 231);
    assert!(past_end["items"].as_array().unwrap().is_empty());
    let (_, filtered) = get(
        &app,
        &token,
        &format!("{url}&search=ENTRY-02&order=created_desc&limit=2"),
    )
    .await;
    assert_eq!(filtered["total"], 31);
    assert_eq!(filtered["items"][0]["data"]["name"], "entry-0230");
    assert_eq!(filtered["items"][1]["data"]["name"], "entry-0229");
    assert_eq!(
        get(&app, &token, &format!("{url}&search=%25")).await.1["total"],
        0
    );
    assert_eq!(
        get(&app, &token, &format!("{url}&order=invalid")).await.0,
        422
    );
    assert_eq!(
        get(&app, &token, &format!("{url}&search={}", "a".repeat(256)))
            .await
            .0,
        422
    );
    assert_eq!(
        get(&app, &token, &format!("{url}&search={}", "a".repeat(255)))
            .await
            .0,
        200
    );
    let path = format!("/folders/{}", root.id);
    assert_eq!(
        content_request(app.clone(), &token, "PATCH", &path, r#"{"name":"renamed"}"#).await,
        204
    );
    assert_eq!(
        db::folder(&e.pool, grandchild.id).await.unwrap().path,
        grandchild.path
    );
    let (_, deep) = get(
        &app,
        &token,
        &format!(
            "/control-plane/v1/spaces/{}/entries?parent_id={}",
            team.id, grandchild.id
        ),
    )
    .await;
    assert_eq!(deep["ancestors"].as_array().unwrap().len(), 3);
    assert_eq!(deep["ancestors"][0]["name"], "renamed");
    let doc = document(team.id, Some(grandchild.id), "kept.txt");
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();
    assert_eq!(
        content_request(app.clone(), &token, "DELETE", &path, "").await,
        409
    );
    assert_eq!(get(&app, &token, &url).await.1["total"], 231);
    assert!(db::folder(&e.pool, grandchild.id).await.is_ok());
    assert!(db::document(&e.pool, doc.id).await.is_ok());
    for method in ["DELETE", "PATCH"] {
        assert_eq!(
            content_request(
                app.clone(),
                &identity.token("reader"),
                method,
                &path,
                r#"{"name":"denied"}"#
            )
            .await,
            403
        );
    }
    // Fixture-only document removal: no product document mutation is introduced.
    sqlx::query("delete from document where id=$1")
        .bind(doc.id)
        .execute(&e.pool)
        .await
        .unwrap();
    assert_eq!(
        content_request(app.clone(), &token, "DELETE", &path, "").await,
        204
    );
    assert_eq!(get(&app, &token, &url).await.0, 404);
    let remaining: i64 = sqlx::query_scalar("select count(*) from folder where space_id=$1")
        .bind(team.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(remaining, 0);
    assert_eq!(content_request(app, &token, "DELETE", &path, "").await, 404);
}
