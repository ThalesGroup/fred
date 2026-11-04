// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    body::{Body, to_bytes},
    http::Request,
};
use control_plane::{
    api::{AppState, routes},
    auth::Authenticator,
    config::Configuration,
    keycloak::Directory,
};
use serde_json::{Value, json};
use tower::ServiceExt;

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn only_control_planes_own_workload_can_manage_runtime_state() {
    let e = env().await;
    let identity = support::IdentityServer::start().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = identity.realm.clone();
    config.security.m2m = None;
    config.security.delegation.accept_delegated_calls = true;
    config.security.delegation.service_accounts_only = true;
    let auth = Authenticator::start(config.security().unwrap())
        .await
        .unwrap();
    let app = routes(AppState {
        pool: e.pool.clone(),
        auth: std::sync::Arc::new(auth),
        onboarding: control_plane::onboarding::Onboarding {
            gcu_version: Some("v1".into()),
            ..Default::default()
        },
        agent_catalog: Default::default(),
        lifecycle: Default::default(),
        directory: Some(
            Directory::new(&identity.realm, "control-plane", "synthetic-secret".into()).unwrap(),
        ),
        content: None,
        processing: None,
    });
    let now = chrono::Utc::now().timestamp();
    let claims = json!({
        "sub":"control-plane-service-subject", "preferred_username":"service-account-control-plane",
        "azp":"control-plane", "client_id":"control-plane", "iss":identity.realm,
        "aud":"fred-delegation", "iat":now, "exp":now+300,
        "resource_access":{"fred-delegation":{"roles":["delegation_caller"]}}
    });
    async fn call(app: &axum::Router, token: &str, query: &str, permission: &str) -> (u16, Value) {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!("/authorize/platform{query}"))
                    .header("authorization", format!("Bearer {token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"permission":permission}).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status().as_u16();
        if status == 200 {
            assert_eq!(response.headers()["cache-control"], "no-store");
        }
        (
            status,
            serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap(),
        )
    }
    let token = identity.sign(claims.clone());
    assert_eq!(
        call(&app, &token, "", "manage_platform").await,
        (200, json!({"allowed":true}))
    );
    assert_eq!(call(&app, &token, "", "administer_users").await.0, 403);
    for query in [
        "?person=alice",
        "?run=run",
        "?agent=agent",
        "?person=alice&run=run",
        "?unknown=x",
    ] {
        assert_eq!(
            call(&app, &token, query, "manage_platform").await.0,
            422,
            "{query}"
        );
    }
    // A complete delegated assertion remains the person's decision, including consent.
    let assertion = "?person=alice&run=run&agent=agent";
    assert_eq!(
        call(&app, &token, assertion, "manage_platform").await.0,
        403
    );
    control_plane::onboarding::accept(&e.pool, Some("v1"), "alice", "v1")
        .await
        .unwrap();
    assert_eq!(
        call(&app, &token, assertion, "manage_platform").await,
        (200, json!({"allowed":false}))
    );
    // Neither an unrelated service nor a human using the CP client inherits its power.
    let mut other = claims.clone();
    other["azp"] = json!("other");
    other["client_id"] = json!("other");
    other["preferred_username"] = json!("service-account-other");
    assert_eq!(
        call(&app, &identity.sign(other), "", "manage_platform")
            .await
            .0,
        403
    );
    let mut person = claims.clone();
    person["sub"] = json!("alice");
    person["preferred_username"] = json!("alice");
    person["aud"] = json!("app");
    person.as_object_mut().unwrap().remove("resource_access");
    assert_eq!(
        call(&app, &identity.sign(person), "", "manage_platform").await,
        (200, json!({"allowed":false}))
    );
    // Invalid provenance is rejected by JWT verification before this exception.
    let mut forged = claims.clone();
    forged["iss"] = json!("https://other.invalid/realms/fred");
    assert_eq!(
        call(&app, &identity.sign(forged), "", "manage_platform")
            .await
            .0,
        401
    );
    let mut expired = claims;
    expired["iat"] = json!(now - 1000);
    expired["exp"] = json!(now - 900);
    assert_eq!(
        call(&app, &identity.sign(expired), "", "manage_platform")
            .await
            .0,
        401
    );
}
