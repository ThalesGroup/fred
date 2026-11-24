// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Team and project conversation purge settings use the existing policy and admission lock.
//! A project without its own value follows its parent team's configured value.
use axum::{Json, extract::State};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use super::policy::{Catalog, Retention};
use crate::{
    api::AppState,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};

#[derive(Debug, Serialize, ToSchema)]
pub struct ConversationRetention {
    /// NULL inherits; zero is immediate purge eligibility.
    #[schema(required = true)]
    pub configured_seconds: Option<i64>,
    /// The parent team's configured value for a project, otherwise the policy.
    pub inherited_seconds: u64,
    /// True when `inherited_seconds` is the parent team's configured value.
    pub inherited_from_team: bool,
    #[schema(required = true)]
    pub organization_ceiling_seconds: Option<u64>,
    pub effective_seconds: u64,
}

impl ConversationRetention {
    fn resolve(
        catalog: &Catalog,
        space: &Space,
        configured_seconds: Option<i64>,
        team_seconds: Option<i64>,
    ) -> AppResult<Self> {
        let nonnegative = |seconds: Option<i64>| {
            seconds
                .map(u64::try_from)
                .transpose()
                .map_err(|_| AppError::BadRequest("retention must be nonnegative".into()))
        };
        let team_seconds = nonnegative(team_seconds)?;
        let inherited_seconds = team_seconds.unwrap_or_else(|| {
            catalog
                .resolve(space.id, space.kind)
                .0
                .retention
                .duration()
                .as_secs()
        });
        let organization_ceiling_seconds = catalog
            .resolve(space.organization, SpaceKind::Organization)
            .0
            .conversation_retention_ceiling
            .map(|v| v.duration().as_secs());
        let selected = nonnegative(configured_seconds)?.unwrap_or(inherited_seconds);
        let effective_seconds =
            organization_ceiling_seconds.map_or(selected, |max| selected.min(max));
        Retention::from_seconds(effective_seconds)?;
        Ok(Self {
            configured_seconds,
            inherited_seconds,
            inherited_from_team: team_seconds.is_some(),
            organization_ceiling_seconds,
            effective_seconds,
        })
    }
}

/// The space's own value and, for a project, its parent team's value.
async fn configured<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: &Space,
) -> AppResult<(Option<i64>, Option<i64>)> {
    Ok(sqlx::query_as(
        "select s.conversation_retention_seconds, t.conversation_retention_seconds
        from space s left join space t on t.id=s.parent_id and s.kind='project'
        where s.id=$1",
    )
    .bind(space.id)
    .fetch_one(ex)
    .await?)
}

pub(crate) async fn read<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    catalog: &Catalog,
    space: &Space,
) -> AppResult<ConversationRetention> {
    let (own, team) = configured(ex, space).await?;
    ConversationRetention::resolve(catalog, space, own, team)
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceConversationRetention {
    /// NULL restores inheritance; zero requests immediate eligibility.
    #[schema(required = true, minimum = 0)]
    #[serde(deserialize_with = "Option::deserialize")]
    pub configured_seconds: Option<i64>,
}

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(
        team_conversation_retention,
        replace_team_conversation_retention
    ))
}

#[utoipa::path(get, path = "/spaces/{id}/conversation-retention", params(("id" = Uuid, Path)),
    responses((status = 200, body = ConversationRetention), (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody)))]
async fn team_conversation_retention(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<ConversationRetention>> {
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, id, Permission::Manage).await?;
    if !matches!(space.kind, SpaceKind::Team | SpaceKind::Project) {
        return Err(AppError::NotFound);
    }
    let settings = read(&mut *tx, &s.lifecycle.catalog, &space).await?;
    tx.commit().await?;
    Ok(Json(settings))
}

#[utoipa::path(put, path = "/spaces/{id}/conversation-retention", params(("id" = Uuid, Path)), request_body = ReplaceConversationRetention,
    responses((status = 200, body = ConversationRetention), (status = 400, body = crate::error::ErrorBody),
    (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
    (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody)))]
async fn replace_team_conversation_retention(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(req): ApiJson<ReplaceConversationRetention>,
) -> AppResult<Json<ConversationRetention>> {
    let (mut tx, space) =
        spaces::governance_mutation(&s.pool, &user.uid, id, Permission::Manage).await?;
    if !matches!(space.kind, SpaceKind::Team | SpaceKind::Project) {
        return Err(AppError::NotFound);
    }
    if let Some(seconds) = req.configured_seconds {
        let seconds = u64::try_from(seconds)
            .map_err(|_| AppError::BadRequest("retention must be nonnegative".into()))?;
        Retention::from_seconds(seconds)
            .map_err(|_| AppError::BadRequest("retention exceeds timestamp range".into()))?;
    }
    let (_, team) = configured(&mut *tx, &space).await?;
    let settings =
        ConversationRetention::resolve(&s.lifecycle.catalog, &space, req.configured_seconds, team)?;
    if let (Some(seconds), Some(max)) = (
        req.configured_seconds,
        settings.organization_ceiling_seconds,
    ) && seconds as u64 > max
    {
        return Err(AppError::BadRequest(
            "retention exceeds organization ceiling".into(),
        ));
    }
    sqlx::query("update space set conversation_retention_seconds=$2 where id=$1")
        .bind(id)
        .bind(req.configured_seconds)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(Json(settings))
}
