// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{Router, http::StatusCode, routing::get};
use control_plane::{
    agents::{PlatformConfig, RuntimeCatalogSource, template_id},
    api::{AppState, routes},
};
use serde_json::json;
use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};
use support::request;

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn default_off_is_authorized_idempotent_and_independent_of_catalogs() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let hits = Arc::new(AtomicUsize::new(0));
    let observed = hits.clone();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base_url = format!("http://{}", listener.local_addr().unwrap());
    let pod = tokio::spawn(async move {
        axum::serve(
            listener,
            Router::new().route(
                "/agents/templates",
                get(move || {
                    observed.fetch_add(1, Ordering::SeqCst);
                    async { StatusCode::SERVICE_UNAVAILABLE }
                }),
            ),
        )
        .await
        .unwrap();
    });
    let app = routes(AppState {
        history: None,
        pool: e.pool.clone(),
        agent_catalog: PlatformConfig {
            runtime_catalog_sources: vec![RuntimeCatalogSource {
                runtime_id: "offline".into(),
                base_url,
                public_base_url: None,
                enabled: true,
            }],
            ..Default::default()
        },
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let template = template_id(org.id, "offline", "custom");
    authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        template,
        true,
    )
    .await
    .unwrap();
    assert!(
        authorization::can_use_agent(&e.pool, template, &team)
            .await
            .unwrap()
    );
    let path = format!("/organizations/{}/agents/{template}/default-on", org.id);
    let (status, _) = request(
        &app,
        &identity,
        Some("bob"),
        "PUT",
        &path,
        json!({"default_on": false}),
    )
    .await;
    assert_eq!(status, 403);
    assert!(
        authorization::agent_default_on(&e.pool, org.id, template)
            .await
            .unwrap()
    );
    for id in [template, template, Uuid::new_v4()] {
        let path = format!("/organizations/{}/agents/{id}/default-on", org.id);
        let (status, body) = request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            json!({"default_on": false}),
        )
        .await;
        assert_eq!(status, 200, "{body}");
        assert_eq!(body["default_on"], false);
        assert!(
            !authorization::agent_default_on(&e.pool, org.id, id)
                .await
                .unwrap()
        );
    }
    assert!(
        !authorization::can_use_agent(&e.pool, template, &team)
            .await
            .unwrap()
    );
    assert_eq!(hits.load(Ordering::SeqCst), 0);
    // Enabling an unverified UUID remains forbidden by catalog availability.
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &path,
        json!({"default_on": true}),
    )
    .await;
    assert_eq!(status, 503, "{body}");
    assert!(
        !authorization::agent_default_on(&e.pool, org.id, template)
            .await
            .unwrap()
    );
    assert_eq!(hits.load(Ordering::SeqCst), 1);
    pod.abort();
}
