// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization-owned team/personal-class positions over the permitted catalogue.
//! Local owners can further restrict them, never bypass this organization ceiling.

use std::collections::BTreeSet;

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use super::{
    config::bounded_text,
    instance::{ModelOfferKey, RuntimeModels},
    local_policy::{SpaceModelPolicy, apply_policy},
    policy,
};
use crate::{
    api::AppState,
    authorization,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    spaces,
};

#[derive(Clone, Copy, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelScopeChoice {
    Disabled,
    Default,
    Enabled,
}

impl From<Option<bool>> for ModelScopeChoice {
    fn from(value: Option<bool>) -> Self {
        match value {
            None => Self::Default,
            Some(false) => Self::Disabled,
            Some(true) => Self::Enabled,
        }
    }
}

#[derive(Serialize, ToSchema)]
pub struct ModelTeamAccess {
    pub team_id: Uuid,
    pub name: String,
    pub choice: ModelScopeChoice,
    /// Organization permission and the team's own restriction, not provider readiness.
    pub effective: bool,
    pub locally_disabled: bool,
}

#[derive(Serialize, ToSchema)]
pub struct ModelAccessMatrix {
    /// Shared organization policy revision; all administrative writes serialize there.
    pub revision: i64,
    pub organization_permitted: bool,
    pub personal: ModelScopeChoice,
    pub personal_effective: bool,
    pub teams: Vec<ModelTeamAccess>,
    pub next_cursor: Option<Uuid>,
}

#[derive(Deserialize)]
pub struct ModelAccessQuery {
    pub upstream_model_id: String,
    pub after: Option<Uuid>,
    pub name: Option<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetModelAccess {
    pub expected_revision: i64,
    pub upstream_model_id: String,
    /// Null explicitly addresses all personal spaces; no individual-user overrides.
    #[serde(deserialize_with = "Option::deserialize")]
    #[schema(required = true)]
    pub team_id: Option<Uuid>,
    pub choice: ModelScopeChoice,
}

async fn require_offer(
    conn: &mut PgConnection,
    organization: Uuid,
    key: &ModelOfferKey,
) -> AppResult<()> {
    if !bounded_text(&key.upstream_model_id, 256) {
        return Err(AppError::Unprocessable("Invalid model identifier.".into()));
    }
    let exists: bool = sqlx::query_scalar(
        "select exists(select 1 from model_offer o join organization_model_source a using(source_id)
         where o.source_id=$1 and o.upstream_model_id=$2 and a.organization_id=$3)",
    )
    .bind(&key.source_id)
    .bind(&key.upstream_model_id)
    .bind(organization)
    .fetch_one(conn)
    .await?;
    if !exists {
        return Err(AppError::NotFound);
    }
    Ok(())
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(model_access_matrix, set_model_access))
}

#[utoipa::path(get,path="/organizations/{organization_id}/model-sources/{source_id}/access",
    params(("organization_id"=Uuid,Path),("source_id"=String,Path),("upstream_model_id"=String,Query),("after"=Option<Uuid>,Query),("name"=Option<String>,Query)),
    responses((status=200,body=ModelAccessMatrix),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn model_access_matrix(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, source_id)): ApiPath<(Uuid, String)>,
    ApiQuery(query): ApiQuery<ModelAccessQuery>,
) -> AppResult<Json<ModelAccessMatrix>> {
    authorization::authorize_organization(&s.pool, &user.uid, organization, Permission::Manage)
        .await?;
    if query.name.as_ref().is_some_and(|name| name.len() > 256) {
        return Err(AppError::Unprocessable("Team filter is too long.".into()));
    }
    let key = ModelOfferKey {
        source_id,
        upstream_model_id: query.upstream_model_id,
    };
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    require_offer(&mut tx, organization, &key).await?;
    let policy = policy::read(&mut tx, organization).await?;
    let permitted = policy.permitted.contains(&key);
    let personal: Option<bool> = sqlx::query_scalar("select enabled from organization_model_scope where organization_id=$1 and source_id=$2 and upstream_model_id=$3 and team_id is null")
        .bind(organization).bind(&key.source_id).bind(&key.upstream_model_id).fetch_optional(&mut *tx).await?;
    let rows: Vec<(Uuid, String, Option<bool>, bool)> = sqlx::query_as(
        "select t.id,t.name,a.enabled,exists(select 1 from space_model_setting l where l.space_id=t.id and l.source_id=$2 and l.upstream_model_id=$3 and l.disabled)
         from space t left join organization_model_scope a on a.organization_id=$1 and a.source_id=$2 and a.upstream_model_id=$3 and a.team_id=t.id
         where t.organization_id=$1 and t.kind='team' and t.deletion_id is null
             and ($4::uuid is null or t.id>$4) and position(lower($5) in lower(t.name))>0 order by t.id limit 101")
        .bind(organization).bind(&key.source_id).bind(&key.upstream_model_id).bind(query.after)
        .bind(query.name.as_deref().unwrap_or("")).fetch_all(&mut *tx).await?;
    let next_cursor = (rows.len() > 100).then(|| rows[99].0);
    let teams = rows
        .into_iter()
        .take(100)
        .map(
            |(team_id, name, enabled, locally_disabled)| ModelTeamAccess {
                team_id,
                name,
                choice: enabled.into(),
                effective: permitted && enabled != Some(false) && !locally_disabled,
                locally_disabled,
            },
        )
        .collect();
    tx.commit().await?;
    authorization::authorize_organization(&s.pool, &user.uid, organization, Permission::Manage)
        .await?;
    Ok(Json(ModelAccessMatrix {
        revision: policy.revision,
        organization_permitted: permitted,
        personal: personal.into(),
        personal_effective: permitted && personal != Some(false),
        teams,
        next_cursor,
    }))
}

#[utoipa::path(put,path="/organizations/{organization_id}/model-sources/{source_id}/access",
    params(("organization_id"=Uuid,Path),("source_id"=String,Path)),request_body=SetModelAccess,
    responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn set_model_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, source_id)): ApiPath<(Uuid, String)>,
    ApiJson(input): ApiJson<SetModelAccess>,
) -> AppResult<StatusCode> {
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    let policy = policy::read(&mut tx, organization).await?;
    if policy.revision == 0 || policy.revision != input.expected_revision {
        return Err(AppError::Conflict(
            "Model policy changed; reload before saving.".into(),
        ));
    }
    let key = ModelOfferKey {
        source_id,
        upstream_model_id: input.upstream_model_id,
    };
    require_offer(&mut tx, organization, &key).await?;
    if let Some(team) = input.team_id {
        let active: bool = sqlx::query_scalar("select exists(select 1 from space where id=$1 and organization_id=$2 and kind='team' and deletion_id is null)")
            .bind(team).bind(organization).fetch_one(&mut *tx).await?;
        if !active {
            return Err(AppError::NotFound);
        }
    }
    if matches!(input.choice, ModelScopeChoice::Enabled) {
        if !policy.permitted.contains(&key) {
            return Err(AppError::Unprocessable(
                "The organization must permit this model first.".into(),
            ));
        }
        policy::require_selectable(
            &mut tx,
            organization,
            &BTreeSet::from([key.clone()]),
            &[(policy::Use::Chat, &key)],
        )
        .await?;
    }
    if matches!(input.choice, ModelScopeChoice::Default) {
        sqlx::query("delete from organization_model_scope where organization_id=$1 and source_id=$2 and upstream_model_id=$3 and team_id is not distinct from $4")
            .bind(organization).bind(&key.source_id).bind(&key.upstream_model_id).bind(input.team_id).execute(&mut *tx).await?;
    } else {
        sqlx::query("insert into organization_model_scope(organization_id,source_id,upstream_model_id,team_id,enabled,updated_by) values($1,$2,$3,$4,$5,$6) on conflict(organization_id,source_id,upstream_model_id,team_id) do update set enabled=excluded.enabled,updated_by=excluded.updated_by,updated_at=clock_timestamp()")
            .bind(organization).bind(&key.source_id).bind(&key.upstream_model_id).bind(input.team_id).bind(matches!(input.choice,ModelScopeChoice::Enabled)).bind(&user.uid).execute(&mut *tx).await?;
    }
    sqlx::query("update organization_model_policy set revision=revision+1,updated_by=$2,updated_at=clock_timestamp() where organization_id=$1")
        .bind(organization).bind(&user.uid).execute(&mut *tx).await?;
    tx.commit().await?;
    tracing::info!(target:"fred.security.audit",audit_event="model.scope_changed",actor_uid=%user.uid,organization_id=%organization,source_id=%key.source_id,upstream_model_id=%key.upstream_model_id,team_id=?input.team_id);
    Ok(StatusCode::NO_CONTENT)
}

/// Reuse the local restriction projection in every picker, preparation and turn admission.
pub(super) async fn apply(
    conn: &mut PgConnection,
    space: &Space,
    models: &mut RuntimeModels,
) -> AppResult<()> {
    let team = if space.kind == SpaceKind::Team {
        Some(space.id)
    } else {
        space.path.get(1).copied()
    };
    // Only organization-permitted offers need a further restriction (at most 4096).
    let rows:Vec<(String,String)>=sqlx::query_as("select a.source_id,a.upstream_model_id from organization_model_scope a join organization_model_permission p using(organization_id,source_id,upstream_model_id) where a.organization_id=$1 and not a.enabled and ((a.team_id is null and $2) or a.team_id=$3)")
        .bind(space.organization).bind(space.kind == SpaceKind::Personal).bind(team).fetch_all(conn).await?;
    apply_policy(
        models,
        SpaceModelPolicy {
            disabled: rows
                .into_iter()
                .map(|(source_id, upstream_model_id)| ModelOfferKey {
                    source_id,
                    upstream_model_id,
                })
                .collect(),
            ..Default::default()
        },
    );
    Ok(())
}
