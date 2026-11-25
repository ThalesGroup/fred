// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Organization diagnostic inventory. Execution admission remains owned by the
//! resolver; trace ingestion only checks immutable session/runtime provenance.
//!
//! Architectural status: under review. Retained to preserve the existing work;
//! further development is deferred until its scope is agreed. Core logs, metrics
//! and OpenTelemetry tracing take priority. The retained routes are disabled in
//! Weaver; capture and inspection cannot be re-enabled through organization settings.
//! Existing lifecycle erasure remains active.
mod consent;
mod ingest;
mod inspect;
pub mod models;
mod policy;

use crate::{
    api::AppState,
    authorization,
    authorization::RuntimeCaller,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    roles::SpacePermission,
};
use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
};
use chrono::{DateTime, Utc};
use models::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::{PgPool, Postgres, Transaction};
use uuid::Uuid;

#[derive(utoipa::OpenApi)]
#[openapi(components(schemas(TraceCatalogSort, TraceConsentFilter)))]
struct TraceApi;

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::with_openapi(<TraceApi as utoipa::OpenApi>::openapi())
        .merge(policy::routes())
        .merge(ingest::routes())
        .merge(consent::routes())
        .merge(inspect::routes())
        // Keep the implementation dormant while its scope is under review. Block
        // the whole route group, including admission, writes and settings updates.
        .layer(axum::middleware::from_fn(
            |_: axum::extract::Request, _: axum::middleware::Next| async { StatusCode::NOT_FOUND },
        ))
}

#[derive(Clone, sqlx::FromRow)]
struct Conversation {
    session_id: Uuid,
    user_id: String,
    space_id: Uuid,
    organization_id: Uuid,
    runtime_id: String,
    agent_display_name: String,
    title: Option<String>,
}
async fn conversation(pool: &PgPool, session: Uuid) -> AppResult<Conversation> {
    sqlx::query_as("select m.session_id,m.user_id,m.space_id,s.organization_id,m.runtime_id,
        m.agent_display_name,m.title from session_metadata m
        join space s on s.id=m.space_id join space o on o.id=s.organization_id
        where m.session_id=$1 and m.deletion_id is null and s.deletion_id is null and o.deletion_id is null")
        .bind(session).fetch_optional(pool).await?.ok_or(AppError::NotFound)
}
async fn observer(s: &AppState, actor: &str, organization: Uuid) -> AppResult<()> {
    authorization::authorize_organization(
        &s.pool,
        actor,
        organization,
        SpacePermission::ObserveOrganization,
    )
    .await?;
    Ok(())
}
fn wire<T: Serialize>(value: T) -> AppResult<Value> {
    serde_json::to_value(value).map_err(|e| AppError::Internal(e.into()))
}
fn decode<T: serde::de::DeserializeOwned>(value: Value) -> AppResult<T> {
    serde_json::from_value(value).map_err(|e| AppError::Internal(e.into()))
}
fn valid_id(value: &str, length: usize) -> bool {
    !value.is_empty()
        && !matches!(value, "." | "..")
        && value.len() <= length
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_.:-".contains(&c))
}
fn conflict() -> AppError {
    AppError::Conflict("trace_capture_no_longer_writable".into())
}

#[derive(Clone, sqlx::FromRow)]
struct Consent {
    version: Uuid,
    cutoff: Option<Value>,
    title: Option<String>,
    incidents: Value,
}
async fn consent(pool: &PgPool, session: Uuid) -> AppResult<Option<Consent>> {
    Ok(sqlx::query_as(
        "select version,case when expires_at>clock_timestamp() then cutoff end as cutoff,title,case when expires_at>clock_timestamp() then incidents else '[]'::jsonb end as incidents from conversation_trace_consent where session_id=$1",
    )
    .bind(session)
    .fetch_optional(pool)
    .await?)
}
fn grant(c: Option<&Consent>) -> AppResult<Option<TraceConsentGrant>> {
    c.filter(|c| c.cutoff.is_some())
        .map(|c| {
            Ok(TraceConsentGrant {
                grant_id: c.version.to_string(),
                cutoff: decode(c.cutoff.clone().unwrap_or(Value::Null))?,
            })
        })
        .transpose()
}
fn covers(c: Option<&Consent>, exchange: &str, rank: i64) -> bool {
    c.and_then(|c| c.cutoff.as_ref()).is_some_and(|cutoff| {
        cutoff["exchange_id"].as_str() == Some(exchange)
            || cutoff["first_rank"].as_i64().is_some_and(|end| rank < end)
    })
}

static HTTP: std::sync::LazyLock<Result<reqwest::Client, reqwest::Error>> =
    std::sync::LazyLock::new(|| {
        reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .connect_timeout(std::time::Duration::from_secs(3))
            .timeout(std::time::Duration::from_secs(15))
            .build()
    });
async fn runtime_read(
    s: &AppState,
    c: &Conversation,
    headers: &HeaderMap,
    suffix: &str,
    params: &[(&str, String)],
) -> AppResult<Value> {
    let source = s
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .find(|v| v.enabled && v.runtime_id == c.runtime_id)
        .ok_or_else(|| AppError::Unavailable("Trace runtime unavailable".into()))?;
    let authorization = headers
        .get(header::AUTHORIZATION)
        .ok_or(AppError::Forbidden)?;
    let client = HTTP
        .as_ref()
        .map_err(|_| AppError::Unavailable("Trace runtime unavailable".into()))?;
    let url = format!(
        "{}/agents/sessions/{}/{}",
        source.base_url.trim_end_matches('/'),
        c.session_id,
        suffix
    );
    let mut response = client
        .get(url)
        .header(header::AUTHORIZATION, authorization)
        .query(params)
        .send()
        .await
        .map_err(|_| AppError::Unavailable("Trace runtime unavailable".into()))?;
    if response.status() == StatusCode::FORBIDDEN || response.status() == StatusCode::UNAUTHORIZED {
        return Err(AppError::Forbidden);
    }
    if !response.status().is_success() {
        return Err(AppError::Unavailable("Trace evidence unavailable".into()));
    }
    let mut body = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| AppError::Unavailable("Trace evidence unavailable".into()))?
    {
        if body.len() + chunk.len() > 16 * 1024 * 1024 {
            return Err(AppError::Unprocessable("Trace response too large".into()));
        }
        body.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&body)
        .map_err(|_| AppError::Unavailable("Invalid trace response".into()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request};
    use std::sync::Arc;
    use tower::ServiceExt;

    #[tokio::test]
    async fn retained_trace_routes_are_disabled_before_any_handler_runs() {
        let config: crate::config::Configuration =
            serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
        let mut security = config.security().unwrap();
        security.enabled = false;
        security.profile_c3 = false;
        let state = AppState {
            // No database or identity server: reaching a handler would fail this test.
            pool: sqlx::postgres::PgPoolOptions::new()
                .connect_lazy("postgres://unused:unused@127.0.0.1:1/unused")
                .unwrap(),
            auth: Arc::new(crate::auth::Authenticator::start(security).await.unwrap()),
            history: None,
            agent_catalog: Default::default(),
            onboarding: Default::default(),
            lifecycle: Default::default(),
            directory: None,
            content: None,
            processing: None,
        };
        let (app, spec): (axum::Router, _) = routes().with_state(state).split_for_parts();
        let paths = serde_json::to_value(spec.paths).unwrap();
        let paths = paths.as_object().unwrap();
        assert!(!paths.is_empty());
        for (path, item) in paths {
            let uri = path
                .split('/')
                .map(|part| {
                    if part.starts_with('{') {
                        "00000000-0000-0000-0000-000000000001"
                    } else {
                        part
                    }
                })
                .collect::<Vec<_>>()
                .join("/");
            for method in item.as_object().unwrap().keys() {
                if !["get", "post", "put", "patch", "delete"].contains(&method.as_str()) {
                    continue;
                }
                let request = Request::builder()
                    .method(method.to_uppercase().as_str())
                    .uri(&uri)
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from("{}"))
                    .unwrap();
                let response = app.clone().oneshot(request).await.unwrap();
                assert_eq!(response.status(), StatusCode::NOT_FOUND, "{method} {path}");
            }
        }
    }
}
