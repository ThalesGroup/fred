// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Personal consent is independent of root authority and space membership.
use std::sync::Arc;

use axum::{
    extract::{FromRef, FromRequestParts},
    http::request::Parts,
    response::{IntoResponse, Response},
};
use chrono::{DateTime, Utc};
use serde::Serialize;
use sqlx::PgPool;

use crate::{
    auth::{Authenticator, CurrentUser},
    config::Configuration,
    error::{AppError, AppResult},
};

#[derive(Clone, Default)]
pub struct Onboarding {
    pub gcu_version: Option<String>,
    pub bootstrap_token_env_var: Option<String>,
    pub user_auth: PublicAuth,
    pub user_directory: crate::users::DirectoryKind,
}

#[derive(Clone, Default, Serialize, utoipa::ToSchema)]
pub struct PublicAuth {
    pub enabled: bool,
    pub realm_url: String,
    pub client_id: String,
    pub provider: String,
    pub uid_claim: String,
    pub roles_claim: Option<Vec<String>>,
}

impl From<&Configuration> for Onboarding {
    fn from(config: &Configuration) -> Self {
        let user = &config.security.user;
        Self {
            user_directory: config.security.user_directory,
            gcu_version: config.app.gcu_version.clone().filter(|_| user.enabled),
            bootstrap_token_env_var: config.app.bootstrap_token_env_var.clone(),
            user_auth: PublicAuth {
                enabled: user.enabled,
                realm_url: user.realm_url.clone(),
                client_id: user.client_id.clone(),
                provider: user.provider.clone(),
                uid_claim: user.claims.uid.clone().unwrap_or_else(|| "sub".into()),
                roles_claim: user.roles_claim.clone(),
            },
        }
    }
}

#[derive(sqlx::FromRow, Serialize, utoipa::ToSchema)]
pub struct Acceptance {
    pub version: String,
    #[schema(value_type = String, format = DateTime)]
    pub accepted_at: DateTime<Utc>,
}

pub async fn acceptance(pool: &PgPool, uid: &str) -> AppResult<Option<Acceptance>> {
    Ok(
        sqlx::query_as("select version, accepted_at from terms_acceptance where user_id = $1")
            .bind(uid)
            .fetch_optional(pool)
            .await?,
    )
}

pub async fn require_accepted<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    version: Option<&str>,
    uid: &str,
) -> AppResult<()> {
    if let Some(version) = version
        && !sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from terms_acceptance where user_id = $1 and version = $2)",
        )
        .bind(uid)
        .bind(version)
        .fetch_one(ex)
        .await?
    {
        return Err(AppError::Denied("user_not_accept_gcu".into()));
    }
    Ok(())
}

pub async fn accept(
    pool: &PgPool,
    active: Option<&str>,
    uid: &str,
    version: &str,
) -> AppResult<()> {
    if active != Some(version) {
        return Err(AppError::Conflict("gcu_version_changed".into()));
    }
    // Retrying the same consent keeps its original evidence; only a new version replaces it.
    let result = sqlx::query("insert into terms_acceptance (user_id, version) values ($1, $2) on conflict (user_id) do update set version = excluded.version, accepted_at = now() where terms_acceptance.version <> excluded.version")
        .bind(uid).bind(version).execute(pool).await?;
    if result.rows_affected() != 0 {
        tracing::info!(target: "fred.security.audit", audit_event = "terms.accepted", actor_uid = uid, version, outcome = "succeeded", "[SECURITY] terms.accepted");
    }
    Ok(())
}

pub async fn bootstrap_completed(pool: &PgPool) -> AppResult<bool> {
    Ok(sqlx::query_scalar(
        "select exists(select 1 from platform_bootstrap where granted_at is not null)",
    )
    .fetch_one(pool)
    .await?)
}

#[derive(Clone)]
pub struct AdmissionState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub version: Option<String>,
    pub user_directory: crate::users::DirectoryKind,
}

/// Business handlers use the same consent check as authenticated CLI import.
pub struct AdmittedUser(pub CurrentUser);
impl<S> FromRequestParts<S> for AdmittedUser
where
    S: Send + Sync,
    AdmissionState: FromRef<S>,
    Arc<Authenticator>: FromRef<S>,
{
    type Rejection = Response;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Response> {
        let user = CurrentUser::from_request_parts(parts, state)
            .await
            .map_err(IntoResponse::into_response)?;
        let admission = AdmissionState::from_ref(state);
        crate::users::snapshot(&admission, &user).await;
        if admission.auth.enabled() {
            require_accepted(&admission.pool, admission.version.as_deref(), &user.uid)
                .await
                .map_err(IntoResponse::into_response)?;
        }
        Ok(Self(user))
    }
}

/// Consent and root bootstrap never accept an asserted subject or a service identity.
pub struct OwnUser(pub CurrentUser);
impl<S> FromRequestParts<S> for OwnUser
where
    S: Send + Sync,
    AdmissionState: FromRef<S>,
    Arc<Authenticator>: FromRef<S>,
{
    type Rejection = Response;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Response> {
        let user = CurrentUser::from_request_parts(parts, state)
            .await
            .map_err(IntoResponse::into_response)?;
        if user.service_account
            || user.roles.iter().any(|role| role == "service_agent")
            || parts.uri.query().is_some()
        {
            return Err(AppError::Forbidden.into_response());
        }
        crate::users::snapshot(&AdmissionState::from_ref(state), &user).await;
        Ok(Self(user))
    }
}
