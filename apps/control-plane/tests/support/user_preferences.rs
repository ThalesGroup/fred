// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{env, support};
use axum::{
    Router,
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
    app: &Router,
    token: Option<String>,
    method: &str,
    path: &str,
    body: Value,
) -> (u16, Value) {
    let mut request = Request::builder()
        .method(method)
        .uri(path)
        .header("content-type", "application/json");
    if let Some(token) = token {
        request = request.header("authorization", format!("Bearer {token}"));
    }
    let response = app
        .clone()
        .oneshot(request.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    let status = response.status().as_u16();
    let body = to_bytes(response.into_body(), 65536).await.unwrap();
    (status, serde_json::from_slice(&body).unwrap())
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn preferences_are_personal_before_consent_and_patch_only_submitted_fields() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    let app = routes(AppState {
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        authorization: e.authorization.clone(),
        directory: None,
        content: None,
        processing: None,
        lifecycle: Default::default(),
        onboarding: Onboarding {
            gcu_version: Some("v1".into()),
            ..Default::default()
        },
    });
    let path = "/users/me/preferences";
    let defaults = json!({"initialized": false, "ui_theme_id": null, "theme_mode": "system",
        "language": null, "sidebar_collapsed": false, "team_sort_mode": "recent", "agent_sort": "name"});
    assert_eq!(request(&app, None, "GET", path, Value::Null).await.0, 401);
    assert_eq!(
        request(
            &app,
            Some(identity.token("alice")),
            "GET",
            "/me",
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(
            &app,
            Some(identity.token("alice")),
            "GET",
            path,
            Value::Null
        )
        .await,
        (200, defaults.clone())
    );
    let selected = json!({"ui_theme_id":"acme", "theme_mode":"dark", "language":"fr",
        "sidebar_collapsed":true, "team_sort_mode":"alpha", "agent_sort":"updated_at:desc"});
    let (status, saved) = request(
        &app,
        Some(identity.token("alice")),
        "PATCH",
        path,
        selected.clone(),
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(saved["initialized"], true);
    for (key, value) in selected.as_object().unwrap() {
        assert_eq!(&saved[key], value);
    }
    assert_eq!(
        request(&app, Some(identity.token("bob")), "GET", path, Value::Null).await,
        (200, defaults.clone())
    );
    for invalid in [
        json!({}),
        json!({"ui_theme_id":""}),
        json!({"ui_theme_id":"Cloud"}),
        json!({"ui_theme_id":"a".repeat(33)}),
        json!({"theme_mode":"midnight"}),
        json!({"language":"de"}),
        json!({"sidebar_collapsed":"false"}),
        json!({"team_sort_mode":"random"}),
        json!({"agent_sort":"rating"}),
        json!({"pane_widths":{}}),
        json!({"trace_expanded":true}),
        json!({"user_id":"bob"}),
    ] {
        assert_eq!(
            request(&app, Some(identity.token("alice")), "PATCH", path, invalid)
                .await
                .0,
            422
        );
    }
    assert_eq!(
        request(
            &app,
            Some(identity.token("alice")),
            "GET",
            path,
            Value::Null
        )
        .await
        .1,
        saved
    );
    assert_eq!(
        request(
            &app,
            Some(identity.token("alice")),
            "PATCH",
            "/users/me/preferences?on_behalf_of=bob",
            json!({"language":"en"})
        )
        .await
        .0,
        403
    );
    let now = chrono::Utc::now().timestamp();
    let service = identity.sign(
        json!({"sub":"service", "iss":identity.realm,"aud":"app","iat":now,"exp":now+300,
        "preferred_username":"service-account-manager", "azp":"manager", "client_id":"manager"}),
    );
    assert_eq!(
        request(&app, Some(service), "PATCH", path, json!({"language":"en"}))
            .await
            .0,
        403
    );

    let (language, sort) = tokio::join!(
        request(
            &app,
            Some(identity.token("alice")),
            "PATCH",
            path,
            json!({"language":"en"})
        ),
        request(
            &app,
            Some(identity.token("alice")),
            "PATCH",
            path,
            json!({"agent_sort":"created_at:desc"})
        ),
    );
    assert_eq!((language.0, sort.0), (200, 200));
    let reloaded = request(
        &app,
        Some(identity.token("alice")),
        "GET",
        path,
        Value::Null,
    )
    .await
    .1;
    assert_eq!(reloaded["language"], "en");
    assert_eq!(reloaded["agent_sort"], "created_at:desc");
    assert_eq!(reloaded["theme_mode"], "dark");
    assert_eq!(reloaded["ui_theme_id"], "acme");
    let reset = json!({"ui_theme_id":null,"theme_mode":null,"language":null,"sidebar_collapsed":null,"team_sort_mode":null,"agent_sort":null});
    let mut initialized_defaults = defaults;
    initialized_defaults["initialized"] = json!(true);
    assert_eq!(
        request(&app, Some(identity.token("alice")), "PATCH", path, reset).await,
        (200, initialized_defaults)
    );
}
