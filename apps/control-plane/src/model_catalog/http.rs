// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization Manage gates administration; source approvals remain platform-owned.

use axum::{Json, extract::State, http::StatusCode};
use serde::Serialize;
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
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
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

#[derive(Serialize, ToSchema)]
pub struct OrganizationModelInventory {
    /// Assigned source observations. Presence/chat/discovery are independent of permission.
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
    authorization::authorize_organization(&s.pool, &user.uid, organization_id, Permission::Manage)
        .await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let inventory = OrganizationModelInventory {
        sources: store::read_inventory(&mut tx, None, Some(organization_id)).await?,
        policy: policy::read(&mut tx, organization_id).await?,
    };
    tx.commit().await?;
    authorization::authorize_organization(&s.pool, &user.uid, organization_id, Permission::Manage)
        .await?;
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
    authorization::authorize_organization(&s.pool, &user.uid, organization_id, Permission::Manage)
        .await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let policy = policy::read(&mut tx, organization_id).await?;
    tx.commit().await?;
    authorization::authorize_organization(&s.pool, &user.uid, organization_id, Permission::Manage)
        .await?;
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
    let (mut tx, _) = spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization_id),
        Permission::Manage,
    )
    .await?;
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
    let (mut tx, _) = spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization_id),
        Permission::Manage,
    )
    .await?;
    let source = s
        .agent_catalog
        .model_sources
        .iter()
        .find(|source| source.source_id == source_id)
        .ok_or(AppError::NotFound)?;
    policy::require_assigned(
        &mut tx,
        organization_id,
        &std::collections::BTreeSet::from([source_id.clone()]),
    )
    .await?;
    if !source.enabled {
        return Err(AppError::Conflict("model source is disabled".into()));
    }
    let token = store::claim(&mut tx, source)
        .await?
        .ok_or_else(|| AppError::Conflict("model source configuration changed".into()))?;
    tx.commit().await?;
    // No SQL connection or transaction survives the bounded discovery call.
    let result = discovery::discover(source).await;
    let (mut tx, _) = spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization_id),
        Permission::Manage,
    )
    .await?;
    policy::require_assigned(
        &mut tx,
        organization_id,
        &std::collections::BTreeSet::from([source_id]),
    )
    .await?;
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
