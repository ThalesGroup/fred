// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization Manage gates administration; source approvals remain platform-owned.

use axum::{Json, extract::State, http::StatusCode};
use serde::Serialize;
use sqlx::{Postgres, Transaction};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use super::{
    ModelInventory, RefreshResult, discovery,
    policy::{self, OrganizationModelPolicy, ReplaceModelPolicy},
    store,
};
use crate::{
    api::AppState,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::{self, AdmittedUser},
    spaces,
};

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(organization_models))
        .routes(routes!(refresh_model_source))
        .routes(routes!(
            organization_model_policy,
            replace_organization_model_policy
        ))
}

async fn authorize(s: &AppState, uid: &str, organization_id: Uuid) -> AppResult<Space> {
    if s.auth.enabled() {
        onboarding::require_accepted(&s.pool, s.onboarding.gcu_version.as_deref(), uid).await?;
    }
    let org = spaces::authorize(
        &s.pool,
        &s.authorization,
        uid,
        organization_id,
        Permission::Manage,
    )
    .await?;
    if org.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    Ok(org)
}

/// Same lock/guard/fence sequence as capability administration, with renewed consent.
async fn authorized_transaction(
    s: &AppState,
    uid: &str,
    org: &Space,
) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = spaces::lock_for(&s.pool, org).await?;
    if s.auth.enabled() {
        onboarding::require_accepted(&mut *tx, s.onboarding.gcu_version.as_deref(), uid).await?;
    }
    let current = spaces::authorize_locked(&mut tx, uid, org.id, Permission::Manage).await?;
    if current.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }

    Ok(tx)
}

#[derive(Serialize, ToSchema)]
pub struct OrganizationModelInventory {
    /// Shared platform observations. Presence/chat/discovery are independent of permission.
    pub sources: Vec<ModelInventory>,
    /// Only this organization's choices; none is a proof of executability.
    pub policy: OrganizationModelPolicy,
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/models",
    params(("organization_id" = Uuid, Path)),
    responses(
        (status = 200, body = OrganizationModelInventory),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn organization_models(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
) -> AppResult<Json<OrganizationModelInventory>> {
    authorize(&s, &user.uid, organization_id).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let inventory = OrganizationModelInventory {
        sources: store::read_inventory(&mut tx, None).await?,
        policy: policy::read(&mut tx, organization_id).await?,
    };
    tx.commit().await?;
    authorize(&s, &user.uid, organization_id).await?;
    Ok(Json(inventory))
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/model-policy",
    params(("organization_id" = Uuid, Path)),
    responses(
        (status = 200, body = OrganizationModelPolicy),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn organization_model_policy(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
) -> AppResult<Json<OrganizationModelPolicy>> {
    authorize(&s, &user.uid, organization_id).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let policy = policy::read(&mut tx, organization_id).await?;
    tx.commit().await?;
    authorize(&s, &user.uid, organization_id).await?;
    Ok(Json(policy))
}

#[utoipa::path(
    put, path = "/organizations/{organization_id}/model-policy",
    params(("organization_id" = Uuid, Path)), request_body = ReplaceModelPolicy,
    responses(
        (status = 200, body = OrganizationModelPolicy),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, description = "Policy revision conflict or newly selected offer not selectable", body = crate::error::ErrorBody),
        (status = 422, description = "Invalid policy or unknown offer", body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn replace_organization_model_policy(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
    ApiJson(request): ApiJson<ReplaceModelPolicy>,
) -> AppResult<Json<OrganizationModelPolicy>> {
    let org = authorize(&s, &user.uid, organization_id).await?;
    let mut tx = authorized_transaction(&s, &user.uid, &org).await?;
    let policy = policy::replace(&mut tx, organization_id, &user.uid, request).await?;
    tx.commit().await?;
    Ok(Json(policy))
}

#[utoipa::path(
    post, path = "/organizations/{organization_id}/model-sources/{source_id}/refresh",
    params(("organization_id" = Uuid, Path), ("source_id" = String, Path)),
    responses(
        (status = 204, description = "Complete source inventory published; read models for observations"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, description = "Disabled, obsolete or superseded source refresh", body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 502, description = "Invalid or incomplete discovery; last success preserved", body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn refresh_model_source(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, source_id)): ApiPath<(Uuid, String)>,
) -> AppResult<StatusCode> {
    let org = authorize(&s, &user.uid, organization_id).await?;
    let source = s
        .agent_catalog
        .model_sources
        .iter()
        .find(|source| source.source_id == source_id)
        .ok_or(AppError::NotFound)?;
    if !source.enabled {
        return Err(AppError::Conflict("model source is disabled".into()));
    }
    let token = {
        let mut tx = authorized_transaction(&s, &user.uid, &org).await?;
        let token = store::claim(&mut tx, source)
            .await?
            .ok_or_else(|| AppError::Conflict("model source configuration changed".into()))?;
        tx.commit().await?;
        token
    };
    // No SQL connection or transaction survives the bounded discovery call.
    let result = discovery::discover(source).await;
    let mut tx = authorized_transaction(&s, &user.uid, &org).await?;
    let outcome = store::publish(&mut tx, source, token, result).await?;
    tx.commit().await?;
    match outcome {
        RefreshResult::Published => Ok(StatusCode::NO_CONTENT),
        RefreshResult::Superseded => Err(AppError::problem(
            StatusCode::CONFLICT,
            "model_refresh_superseded",
            "A newer refresh or source configuration superseded this result.",
        )),
        RefreshResult::Failed(error) => Err(AppError::problem(
            if error.state() == "unavailable" {
                StatusCode::SERVICE_UNAVAILABLE
            } else {
                StatusCode::BAD_GATEWAY
            },
            "model_discovery_failed",
            "Discovery failed; consult the retained source observation for diagnostics.",
        )),
    }
}
