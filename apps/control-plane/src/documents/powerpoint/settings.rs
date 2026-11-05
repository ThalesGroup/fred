// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! The existing Swift drawer's organization/pod settings. The library validates config.
use super::*;
use crate::{
    api::AppState,
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
};
use axum::{Json, extract::State, http::HeaderMap};
use serde_json::{Value, json};
use utoipa_axum::{router::OpenApiRouter, routes};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Target {
    runtime_id: String,
}

#[derive(Serialize, ToSchema)]
pub struct PowerPointSettings {
    pub current: PowerPointResolution,
    #[schema(required = true)]
    pub replacement: Option<PowerPointResolution>,
    #[schema(value_type = Object)]
    pub config: Value,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
struct PowerPointSettingsChange {
    pub expected_file_id: Option<Uuid>,
    #[schema(value_type = Object)]
    pub config: Value,
}

#[utoipa::path(operation_id="get_powerpoint_settings", get, path="/spaces/{space_id}/powerpoint-template/settings",
    params(("space_id"=Uuid,Path),("runtime_id"=String,Query)), responses((status=200,body=PowerPointSettings),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn get(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Target>,
) -> AppResult<Json<PowerPointSettings>> {
    http::runtime(&s, space, None, Some(&q.runtime_id)).await?;
    // One snapshot for file, preparation and edits; the organization write right
    // matches the existing template administration and capability preview checks.
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let owner = authorization::authorize(&mut *tx, &user.uid, space, Permission::Write).await?;
    target(&mut *tx, &owner, None).await?;
    let effective: Option<PowerPointFile> = sqlx::query_as("select * from powerpoint_file where space_id=$1 and runtime_id=$2 and agent_instance_id is null and status='stored' and effective")
        .bind(space).bind(&q.runtime_id).fetch_optional(&mut *tx).await?;
    let candidate: Option<PowerPointFile> = sqlx::query_as("select f.* from powerpoint_file f where space_id=$1 and runtime_id=$2 and agent_instance_id is null and status='stored' and (not effective or exists(select 1 from capability_preparation p where p.file_id=f.id and p.state in ('pending','failed'))) order by effective limit 1")
        .bind(space).bind(&q.runtime_id).fetch_optional(&mut *tx).await?;
    let config: Option<Value> = sqlx::query_scalar("select config from organization_powerpoint_settings where organization_id=$1 and runtime_id=$2 and file_id is not distinct from $3")
        .bind(space).bind(&q.runtime_id).bind(effective.as_ref().map(|f|f.id)).fetch_optional(&mut *tx).await?;
    let current = resolve_file_preparation(&mut *tx, effective, true).await?;
    let replacement = if candidate.is_some() {
        Some(resolve_file_preparation(&mut *tx, candidate, false).await?)
    } else {
        None
    };
    tx.commit().await?;
    Ok(Json(PowerPointSettings {
        current,
        replacement,
        config: config.unwrap_or_else(|| json!({})),
    }))
}

#[utoipa::path(operation_id="put_powerpoint_settings", put, path="/spaces/{space_id}/powerpoint-template/settings",
    params(("space_id"=Uuid,Path),("runtime_id"=String,Query)), request_body=PowerPointSettingsChange, responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn put(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Target>,
    headers: HeaderMap,
    ApiJson(input): ApiJson<PowerPointSettingsChange>,
) -> AppResult<StatusCode> {
    let runtime = http::runtime(&s, space, None, Some(&q.runtime_id)).await?;
    let owner = authorization::authorize(&s.pool, &user.uid, space, Permission::Write).await?;
    target(&s.pool, &owner, None).await?;
    let stored = crate::agent_instances::tuning::validate_capability_config(
        &s.agent_catalog,
        &runtime,
        headers.get(axum::http::header::AUTHORIZATION),
        "ppt_builder",
        input.config,
    )
    .await?;
    let (mut tx, _) = writer(&s.pool, &user, space, None).await?;
    let effective: Option<Uuid> = sqlx::query_scalar("select id from powerpoint_file where space_id=$1 and runtime_id=$2 and agent_instance_id is null and status='stored' and effective")
        .bind(space).bind(&runtime).fetch_optional(&mut *tx).await?;
    if input.expected_file_id != effective {
        return Err(conflict(
            "powerpoint_file_changed",
            "The effective template changed; reopen the slide review",
        ));
    }
    sqlx::query("insert into organization_powerpoint_settings(organization_id,runtime_id,file_id,config) values($1,$2,$3,$4) on conflict(organization_id,runtime_id) do update set file_id=excluded.file_id,config=excluded.config")
        .bind(space).bind(&runtime).bind(effective).bind(&stored["config"]).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(operation_id="rerun_powerpoint_template", post, path="/spaces/{space_id}/powerpoint-template/prepare",
    params(("space_id"=Uuid,Path),("runtime_id"=String,Query)), request_body=PowerPointChange, responses((status=202),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn rerun(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Target>,
    ApiJson(input): ApiJson<PowerPointChange>,
) -> AppResult<StatusCode> {
    let runtime = http::runtime(&s, space, None, Some(&q.runtime_id)).await?;
    if !s
        .agent_catalog
        .capability_preparation
        .workers
        .contains_key(&runtime)
    {
        return Err(unavailable());
    }
    let (mut tx, owner) = writer(&s.pool, &user, space, None).await?;
    if !crate::agents::enablement::usable_capability_ids(&mut *tx, &owner, &runtime)
        .await?
        .contains("ppt_builder")
    {
        return Err(AppError::Forbidden);
    }
    let row = current(&mut *tx, space, None, &runtime).await?;
    unchanged(input.expected_file_id, row.as_ref())?;
    let row = row.ok_or(AppError::NotFound)?;
    let pending: bool = sqlx::query_scalar(
        "select exists(select 1 from capability_preparation where file_id=$1 and state='pending')",
    )
    .bind(row.file.id)
    .fetch_one(&mut *tx)
    .await?;
    if !pending {
        // Retain the acknowledged analysis until its replacement succeeds.
        sqlx::query("update capability_preparation set state='obsolete' where file_id=$1 and state='failed'")
            .bind(row.file.id).execute(&mut *tx).await?;
        crate::capability_preparation::enqueue(
            &mut tx,
            row.file.id,
            &runtime,
            None,
            &json!({"use_vision":false}),
        )
        .await?;
    }
    tx.commit().await?;
    Ok(StatusCode::ACCEPTED)
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(get, put))
        .routes(routes!(rerun))
}
