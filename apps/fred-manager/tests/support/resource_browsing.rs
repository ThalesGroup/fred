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
    (status, serde_json::from_slice(&body).unwrap())
}

// Proves: I1, I6, I8, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn resource_reads_enforce_scope_and_preserve_cursor_and_role_semantics() {
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
    grant(&e, org.id, Role::PersonalSpaceCreator, "reader").await;
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "reader", org.id)
        .await
        .unwrap()
        .0;
    let folder = |space_id, name: &str, parent: Option<&Folder>| {
        let id = Uuid::new_v4();
        Folder {
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
    let mut expected = Vec::new();
    for i in 0..53 {
        let d = Document {
            id: Uuid::new_v4(),
            space_id: team.id,
            folder_id: Some(root.id),
            name: format!("document-{:02}.txt", i),
            mime: "text/plain".into(),
            size: 1,
            sha256: format!("{i:064x}"),
            created_by: "editor".into(),
        };
        db::insert_document(&e.pool, &d).await.unwrap();
        expected.push(d);
    }
    expected.sort_by(|a, b| (&a.name, a.id).cmp(&(&b.name, b.id)));
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
    let app = fred_manager::api::governance_router(fred_manager::api::GovernanceState {
        onboarding: Default::default(),
        auth: std::sync::Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        fga: observed,
        directory: None,
    });
    let reader = identity.token("reader");
    let base = format!("/spaces/{}", team.id);
    for (suffix, expected_rows) in [("folders", 1), ("documents", 0)] {
        let (status, body) = get(&app, &reader, &format!("{base}/{suffix}")).await;
        assert_eq!(status, 200, "{body}");
        assert_eq!(body.as_array().unwrap().len(), expected_rows);
    }
    let docs = format!("{base}/documents?folder_id={}&limit=50", root.id);
    let (status, first) = get(&app, &reader, &docs).await;
    assert_eq!(status, 200);
    let first = first.as_array().unwrap();
    assert_eq!(first.len(), 50);
    let last = first.last().unwrap();
    let (_, second) = get(
        &app,
        &reader,
        &format!(
            "{docs}&after_name={}&after_id={}",
            last["name"].as_str().unwrap(),
            last["id"].as_str().unwrap()
        ),
    )
    .await;
    let second = second.as_array().unwrap();
    assert_eq!(
        first
            .iter()
            .chain(second.iter())
            .map(|d| d["id"].as_str().unwrap().to_owned())
            .collect::<Vec<_>>(),
        expected
            .iter()
            .map(|d| d.id.to_string())
            .collect::<Vec<_>>()
    );
    assert_eq!(
        get(&app, &reader, &format!("{docs}&after_name=partial"))
            .await
            .0,
        422
    );
    for (suffix, param) in [("folders", "parent_id"), ("documents", "folder_id")] {
        for invalid in [private.id, Uuid::new_v4()] {
            assert_eq!(
                get(&app, &reader, &format!("{base}/{suffix}?{param}={invalid}"))
                    .await
                    .0,
                404
            );
        }
        assert_eq!(
            get(
                &app,
                &reader,
                &format!("{base}/{suffix}?{param}={}", child.id)
            )
            .await,
            (200, serde_json::json!([]))
        );
        for user in ["reader", "editor", "analyst"] {
            assert_eq!(
                get(&app, &identity.token(user), &format!("{base}/{suffix}"))
                    .await
                    .0,
                200
            );
        }
        assert_eq!(
            get(&app, &identity.token("admin"), &format!("{base}/{suffix}"))
                .await
                .0,
            403
        );
        assert_eq!(
            get(
                &app,
                &identity.token("alice"),
                &format!("/spaces/{}/{suffix}", personal.id)
            )
            .await
            .0,
            403
        );
    }
    // Same read budget with 0 or 53 documents, concurrency 1. Force role paging.
    for path in [format!("{base}/documents"), docs.clone()] {
        *proxy.fault.lock().await = support::fga_proxy::Fault {
            read_page_size: Some(1),
            ..Default::default()
        };
        assert_eq!(get(&app, &reader, &path).await.0, 200);
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("check"), Some(&1));
        assert_eq!(fault.writes, 0);
        assert_eq!(fault.calls.len(), 2);
        // 5 direct-role pages + placement of team, team membership and personal.
        assert_eq!(fault.calls.get("read"), Some(&8));
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
    assert_eq!(get(&app, &reader, &format!("{base}/folders")).await.0, 403);
    let other = spaces::create_organization(&e.pool, &e.fga, "Other", "outsider")
        .await
        .unwrap();
    assert_eq!(
        get(&app, &reader, &format!("/spaces/{}/documents", other.id))
            .await
            .0,
        403
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_placement_reads_overlap_with_a_bounded_request_budget() {
    let e = env().await;
    let org = spaces::create_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    grant(&e, org.id, Role::Member, "reader").await;
    // More placements than the cap exercise replenishment as well as concurrency.
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
        read_delay: Some(Duration::from_millis(20)),
        ..Default::default()
    };
    assert_eq!(
        spaces::organization(&e.pool, &observed, "reader")
            .await
            .unwrap(),
        Some(org.id)
    );
    let fault = proxy.fault.lock().await;
    assert_eq!(fault.calls.get("read"), Some(&45)); // five role pages, forty links
    assert_eq!(fault.calls.len(), 1);
    assert_eq!(fault.writes, 0);
    assert!(
        fault.peak_reads > 1 && fault.peak_reads <= 32,
        "peak {}",
        fault.peak_reads
    );
    assert_eq!(fault.active_reads, 0);
}
