// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{sync::Arc, time::Duration};

use axum::{
    Json, Router,
    extract::{FromRef, State},
    http::StatusCode,
    routing::get,
};
use fred_rust_sdk::security::{
    authentication::{Authenticator, CurrentUser},
    platform::is_platform_admin,
};
use serde_json::json;
use sqlx::PgPool;
use utoipa::OpenApi;

use crate::kubernetes::{Kubernetes, Snapshot};

#[derive(Clone)]
pub struct AppState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub kubernetes: Kubernetes,
}

impl FromRef<AppState> for Arc<Authenticator> {
    fn from_ref(state: &AppState) -> Self {
        state.auth.clone()
    }
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(|| async { Json(json!({"status": "ok"})) }))
        .route("/monitor/v1/status", get(status))
        .with_state(state)
}

#[utoipa::path(
    get, path = "/monitor/v1/status", operation_id = "monitor_status",
    responses(
        (status = 200, body = Snapshot),
        (status = 401, description = "Missing or invalid human JWT"),
        (status = 403, description = "Platform administrator required"),
        (status = 503, description = "Authorization database unavailable")
    ),
    security(("bearer" = []))
)]
async fn status(
    State(state): State<AppState>,
    user: CurrentUser,
) -> Result<Json<Snapshot>, StatusCode> {
    // This endpoint admits a person with a database grant, never a delegated workload.
    if user.service_account {
        return Err(StatusCode::FORBIDDEN);
    }
    let allowed = match tokio::time::timeout(
        Duration::from_secs(2),
        is_platform_admin(&state.pool, &user.uid),
    )
    .await
    {
        Ok(Ok(allowed)) => allowed,
        Ok(Err(error)) => {
            tracing::warn!(%error, "platform authorization unavailable");
            return Err(StatusCode::SERVICE_UNAVAILABLE);
        }
        Err(_) => {
            tracing::warn!("platform authorization timed out");
            return Err(StatusCode::SERVICE_UNAVAILABLE);
        }
    };
    if !allowed {
        return Err(StatusCode::FORBIDDEN);
    }
    Ok(Json(state.kubernetes.snapshot().await))
}

pub fn openapi() -> utoipa::openapi::OpenApi {
    #[derive(OpenApi)]
    #[openapi(paths(status))]
    struct ApiDoc;
    let mut api = ApiDoc::openapi();
    if let Some(components) = api.components.as_mut() {
        components.add_security_scheme(
            "bearer",
            utoipa::openapi::security::SecurityScheme::Http(utoipa::openapi::security::Http::new(
                utoipa::openapi::security::HttpAuthScheme::Bearer,
            )),
        );
    }
    api
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request};
    use fred_rust_sdk::security::authentication::{
        DirectoryDelegation, Provider, SecuritySettings, UserClaims,
    };
    use sqlx::postgres::PgPoolOptions;
    use tower::ServiceExt;

    #[tokio::test]
    async fn only_liveness_is_public_even_when_the_database_is_unavailable() {
        let auth = Authenticator::start(SecuritySettings {
            enabled: true,
            provider: Provider::Keycloak,
            realm_url: "http://127.0.0.1:1/realms/test".into(),
            client_id: "fred-ui".into(),
            audience: Some("fred".into()),
            jwks_url: None,
            claims: UserClaims::default(),
            roles_claim: None,
            m2m_realm_url: None,
            directory_delegation: DirectoryDelegation::default(),
            profile_c3: true,
            clock_skew_seconds: 30,
            max_token_lifetime_seconds: 3600.0,
        })
        .await
        .unwrap();
        let app = router(AppState {
            auth: Arc::new(auth),
            kubernetes: Kubernetes::new(
                kube::Client::try_from(kube::Config::new("http://127.0.0.1:1".parse().unwrap()))
                    .unwrap(),
                "test".into(),
            ),
            pool: PgPoolOptions::new()
                .connect_lazy("postgres://unused:unused@127.0.0.1:1/unused")
                .unwrap(),
        });
        for (path, bearer, expected) in [
            ("/healthz", "", StatusCode::OK),
            ("/monitor/v1/status", "", StatusCode::UNAUTHORIZED),
            (
                "/monitor/v1/status",
                "Bearer invalid",
                StatusCode::UNAUTHORIZED,
            ),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(path)
                        .header("authorization", bearer)
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), expected, "{path} with {bearer:?}");
        }
    }
}
