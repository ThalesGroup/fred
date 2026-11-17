// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Application, ApplicationMetadata, SOURCE_ID, all, descriptor};
use crate::{
    api::AppState,
    authorization, bootstrap, domain,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    roles::{PlatformPermission, SpacePermission},
};
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::types::Json as SqlJson;
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(platform_applications, create_application))
        .routes(routes!(update_application))
        .routes(routes!(space_applications))
}
fn default_permission() -> SpacePermission {
    SpacePermission::Read
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateApplication {
    pub logical_name: String,
    pub ui_base_url: String,
    pub api_base_url: Option<String>,
    #[serde(default = "default_permission")]
    pub entry_permission: SpacePermission,
    #[serde(flatten)]
    pub metadata: ApplicationMetadata,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateApplication {
    pub expected_revision: i64,
    pub ui_base_url: String,
    pub api_base_url: Option<String>,
    pub entry_permission: SpacePermission,
    pub enabled: bool,
    #[serde(flatten)]
    pub metadata: ApplicationMetadata,
}

#[derive(Serialize, ToSchema)]
pub struct SpaceApplication {
    pub id: Uuid,
    pub logical_name: String,
    pub source_id: String,
    pub capability_id: String,
    pub entry_permission: SpacePermission,
    pub ui_path: String,
    pub api_path: Option<String>,
    #[serde(flatten)]
    pub metadata: ApplicationMetadata,
}

fn validate(
    metadata: &ApplicationMetadata,
    permission: SpacePermission,
    ui: &str,
    api: Option<&str>,
) -> AppResult<()> {
    let localized = |values: &std::collections::BTreeMap<String, String>, max| {
        values.len() <= 16
            && values.iter().all(|(lang, value)| {
                (2..=16).contains(&lang.len())
                    && lang.bytes().all(|b| b.is_ascii_alphabetic() || b == b'-')
                    && value.chars().count() <= max
                    && !value.chars().any(char::is_control)
            })
    };
    if domain::canonical_name(&metadata.display_name, 255).as_deref()
        != Some(&metadata.display_name)
        || metadata.description.chars().count() > 2000
        || domain::canonical_name(&metadata.icon, 128).as_deref() != Some(&metadata.icon)
        || domain::canonical_name(&metadata.version, 64).as_deref() != Some(&metadata.version)
        || !localized(&metadata.display_name_by_lang, 255)
        || !localized(&metadata.description_by_lang, 2000)
        || matches!(
            permission,
            SpacePermission::AdministerOrganization | SpacePermission::CreatePersonalSpace
        )
    {
        return Err(AppError::Unprocessable(
            "Invalid application description or entry permission.".into(),
        ));
    }
    super::proxy::destination(ui)?;
    if let Some(api) = api {
        super::proxy::destination(api)?;
    }
    Ok(())
}

#[utoipa::path(get, path="/platform/applications", responses((status=200, body=[Application]), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody)))]
async fn platform_applications(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Vec<Application>>> {
    let mut tx = s.pool.begin().await?;
    authorization::require_platform(&mut *tx, &user.uid, PlatformPermission::ManagePlatform)
        .await?;
    let result = all(&mut tx).await?;
    tx.commit().await?;
    Ok(Json(result))
}

#[utoipa::path(post, path="/platform/applications", request_body=CreateApplication, responses((status=201, body=Application), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn create_application(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(body): ApiJson<CreateApplication>,
) -> AppResult<(StatusCode, Json<Application>)> {
    if !domain::valid_logical_name(&body.logical_name) {
        return Err(AppError::Unprocessable(
            "Invalid application logical name.".into(),
        ));
    }
    validate(
        &body.metadata,
        body.entry_permission,
        &body.ui_base_url,
        body.api_base_url.as_deref(),
    )?;
    let id = Uuid::new_v4();
    let mut tx = bootstrap::locked(&s.pool).await?;
    authorization::require_platform(&mut *tx, &user.uid, PlatformPermission::ManagePlatform)
        .await?;
    sqlx::query("insert into application(id,logical_name,ui_base_url,api_base_url,entry_permission,updated_by) values($1,$2,$3,$4,$5,$6)")
        .bind(id).bind(&body.logical_name).bind(&body.ui_base_url).bind(&body.api_base_url)
        .bind(serde_json::to_value(body.entry_permission).map_err(anyhow::Error::from)?.as_str())
        .bind(&user.uid).execute(&mut *tx).await?;
    sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised,application_id) values($1,$2,$3,$4,false,$5)")
        .bind(SOURCE_ID).bind(format!("application:{id}")).bind(&body.metadata.version).bind(SqlJson(descriptor(id,&body.metadata))).bind(id).execute(&mut *tx).await?;
    let app = super::by_name(&mut tx, &body.logical_name).await?;
    tx.commit().await?;
    tracing::info!(target:"fred.security.audit", audit_event="application.registered", actor_uid=%user.uid, application_id=%id);
    Ok((StatusCode::CREATED, Json(app)))
}

#[utoipa::path(put, path="/platform/applications/{application_id}", params(("application_id"=Uuid, Path)), request_body=UpdateApplication, responses((status=200, body=Application), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn update_application(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<UpdateApplication>,
) -> AppResult<Json<Application>> {
    validate(
        &body.metadata,
        body.entry_permission,
        &body.ui_base_url,
        body.api_base_url.as_deref(),
    )?;
    let mut tx = bootstrap::locked(&s.pool).await?;
    authorization::require_platform(&mut *tx, &user.uid, PlatformPermission::ManagePlatform)
        .await?;
    let (revision, name): (i64, String) =
        sqlx::query_as("select revision,logical_name from application where id=$1 for update")
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
    if revision != body.expected_revision {
        return Err(AppError::Conflict(
            "The application changed; refresh before saving.".into(),
        ));
    }
    sqlx::query("update application set ui_base_url=$2,api_base_url=$3,entry_permission=$4,revision=revision+1,updated_by=$5,updated_at=clock_timestamp() where id=$1")
        .bind(id).bind(&body.ui_base_url).bind(&body.api_base_url)
        .bind(serde_json::to_value(body.entry_permission).map_err(anyhow::Error::from)?.as_str()).bind(&user.uid).execute(&mut *tx).await?;
    sqlx::query("update capability_offer set version=$2,descriptor=$3,advertised=$4 where application_id=$1")
        .bind(id).bind(&body.metadata.version).bind(SqlJson(descriptor(id,&body.metadata))).bind(body.enabled).execute(&mut *tx).await?;
    let app = super::by_name(&mut tx, &name).await?;
    tx.commit().await?;
    tracing::info!(target:"fred.security.audit", audit_event="application.updated", actor_uid=%user.uid, application_id=%id, revision=revision+1, enabled=body.enabled);
    Ok(Json(app))
}

#[utoipa::path(get, path="/spaces/{space_id}/applications", params(("space_id"=Uuid, Path)), responses((status=200, body=[SpaceApplication]), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody)))]
async fn space_applications(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Vec<SpaceApplication>>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let facts = authorization::load_facts(&mut *tx, &user.uid, id).await?;
    if !facts.in_organization {
        return Err(AppError::NotFound);
    }
    facts.require_active()?;
    if facts.space.kind == domain::SpaceKind::Personal || facts.direct_roles.is_empty() {
        return Err(AppError::Forbidden);
    }
    let space: domain::Space = facts.space.clone().into();
    let policy = crate::agents::enablement::Policy::load_for_space(&mut *tx, &space).await?;
    let mut result = Vec::new();
    for app in all(&mut tx).await? {
        if !app.enabled
            || authorization::decide(&facts, app.entry_permission).is_err()
            || !crate::agents::enablement::usable(&policy, &space, SOURCE_ID, &app.capability_id)
        {
            continue;
        }
        result.push(SpaceApplication {
            id: app.id,
            ui_path: format!("/apps/{}/", app.logical_name),
            api_path: app
                .api_base_url
                .as_ref()
                .map(|_| format!("/app-services/{}/teams/{id}/", app.logical_name)),
            logical_name: app.logical_name,
            source_id: app.source_id,
            capability_id: app.capability_id,
            entry_permission: app.entry_permission,
            metadata: app.metadata,
        });
    }
    tx.commit().await?;
    Ok(Json(result))
}
