// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{PowerPointChange, PowerPointFile, PowerPointResolution};
use crate::{
    api::AppState,
    documents::{Storage, unavailable},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery, idempotency_key},
    onboarding::AdmittedUser,
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, Multipart, State},
    http::{HeaderMap, StatusCode},
    response::Response,
};
use serde::Deserialize;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Target {
    agent_instance_id: Option<Uuid>,
    runtime_id: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Change {
    agent_instance_id: Option<Uuid>,
    runtime_id: Option<String>,
    template_id: Option<Uuid>,
    expected_file_id: Option<Uuid>,
}
pub(super) async fn runtime(
    s: &AppState,
    space: Uuid,
    agent: Option<Uuid>,
    requested: Option<&str>,
) -> AppResult<String> {
    if let Some(agent) = agent {
        return Ok(crate::agent_instances::get_for_space(&s.pool, space, agent)
            .await?
            .ok_or(AppError::NotFound)?
            .source_runtime_id);
    }
    let id = requested.ok_or_else(|| {
        AppError::Unprocessable("An organization template requires a logical pod".into())
    })?;
    if !s
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .any(|source| source.enabled && source.runtime_id == id)
    {
        return Err(AppError::NotFound);
    }
    Ok(id.to_owned())
}

pub(super) fn storage(s: &AppState) -> AppResult<&Storage> {
    s.content.as_deref().ok_or_else(unavailable)
}

/// Resolve the stored file for this usage. An omitted instance targets only an organization.
/// Preparation metadata comes from acknowledged CP state, scoped to this logical pod.
#[utoipa::path(operation_id="resolve_powerpoint_template", get, path="/spaces/{space_id}/powerpoint-template", params(("space_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query)),responses((status=200,body=PowerPointResolution),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn resolve(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(target): ApiQuery<Target>,
) -> AppResult<Json<PowerPointResolution>> {
    let runtime = runtime(
        &s,
        space,
        target.agent_instance_id,
        target.runtime_id.as_deref(),
    )
    .await?;
    Ok(Json(
        storage(&s)?
            .resolve_powerpoint(&user.uid, space, target.agent_instance_id, &runtime)
            .await?,
    ))
}

/// Stage an agent original, or accept an organization candidate after preflight.
/// Neither this endpoint nor its response activates the file in an executing agent.
#[utoipa::path(operation_id="upload_powerpoint_template", put, path="/spaces/{space_id}/powerpoint-template", params(("space_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query),("template_id"=Option<Uuid>,Query,description="Only for a new draft instance"),("expected_file_id"=Option<Uuid>,Query,description="Current own attachment; omit only if absent"),("Idempotency-Key"=Uuid,Header)),request_body(content=crate::documents::http::FileUpload,content_type="multipart/form-data"),responses((status=200,body=PowerPointFile),(status=400,body=crate::error::ErrorBody),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=408,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=413,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn upload(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(change): ApiQuery<Change>,
    headers: HeaderMap,
    multipart: Multipart,
) -> AppResult<Json<PowerPointFile>> {
    let owner = crate::authorization::authorize(
        &s.pool,
        &user.uid,
        space,
        crate::domain::Permission::Write,
    )
    .await?;
    let runtime = if let Some(template) = change.template_id {
        if change.agent_instance_id.is_none()
            || !crate::authorization::can_use_agent(&s.pool, template, &owner).await?
        {
            return Err(AppError::NotFound);
        }
        crate::agents::enrollable_template(&s.pool, &s.agent_catalog, owner.organization, template)
            .await?
            .0
            .source_runtime_id
    } else {
        runtime(
            &s,
            space,
            change.agent_instance_id,
            change.runtime_id.as_deref(),
        )
        .await?
    };
    if !s
        .agent_catalog
        .capability_preparation
        .workers
        .contains_key(&runtime)
    {
        return Err(AppError::Unavailable(
            "No preparation worker is configured for this logical pod".into(),
        ));
    }
    let usable =
        crate::agents::enablement::usable_capability_ids(&s.pool, &owner, &runtime).await?;
    if !usable.contains("ppt_builder") {
        return Err(AppError::Forbidden);
    }
    let mut file = storage(&s)?
        .upload_powerpoint(
            &user,
            super::PowerPointTarget {
                space_id: space,
                agent: change.agent_instance_id,
                runtime: &runtime,
            },
            idempotency_key(&headers)?,
            PowerPointChange {
                expected_file_id: change.expected_file_id,
            },
            super::PowerPointUpload::Multipart(multipart),
            change.template_id.is_some(),
        )
        .await?;
    if change.agent_instance_id.is_none() && file.status == super::PowerPointFileStatus::Pending {
        let change = crate::capability_preparation::FileChange {
            file_id: Some(file.id),
            expected_file_id: change.expected_file_id,
        };
        let config = serde_json::json!({"use_vision":false});
        super::acceptance::preflight(
            &s,
            &user,
            super::PowerPointTarget {
                space_id: space,
                agent: None,
                runtime: &runtime,
            },
            &change,
            &config,
            headers.get(axum::http::header::AUTHORIZATION),
        )
        .await?;
        let (mut tx, _) = super::writer(&s.pool, &user, space, None).await?;
        super::acceptance::attach(&mut tx, &user, space, None, &runtime, &change).await?;
        crate::capability_preparation::enqueue(&mut tx, file.id, &runtime, None, &config).await?;
        tx.commit().await?;
        file = sqlx::query_as("select * from powerpoint_file where id=$1")
            .bind(file.id)
            .fetch_one(&s.pool)
            .await?;
    }
    Ok(Json(file))
}

/// Detach the own file; physical cleanup is asynchronous and durably recorded.
#[utoipa::path(operation_id="remove_powerpoint_template", delete, path="/spaces/{space_id}/powerpoint-template", params(("space_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query),("expected_file_id"=Option<Uuid>,Query)),responses((status=202,description="Detached; cleanup pending"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn remove(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(change): ApiQuery<Change>,
) -> AppResult<StatusCode> {
    let runtime = runtime(
        &s,
        space,
        change.agent_instance_id,
        change.runtime_id.as_deref(),
    )
    .await?;
    storage(&s)?
        .remove_powerpoint(
            &user,
            space,
            change.agent_instance_id,
            PowerPointChange {
                expected_file_id: change.expected_file_id,
            },
            &runtime,
        )
        .await?;
    Ok(StatusCode::ACCEPTED)
}

/// File identity is checked against the authorized, currently resolved usage.
#[utoipa::path(operation_id="download_powerpoint_template", get, path="/spaces/{space_id}/powerpoint-template/{file_id}/content", params(("space_id"=Uuid,Path),("file_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query)),responses((status=200,body=String,content_type="application/octet-stream"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn content(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, file)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(target): ApiQuery<Target>,
) -> AppResult<Response> {
    let runtime = runtime(
        &s,
        space,
        target.agent_instance_id,
        target.runtime_id.as_deref(),
    )
    .await?;
    storage(&s)?
        .download_powerpoint(&user.uid, space, target.agent_instance_id, file, &runtime)
        .await
}

/// The depositor can follow one operation, including after the agent is removed.
/// This receipt grants no download right and is not a template/version catalogue.
#[utoipa::path(operation_id="powerpoint_upload_receipt", get, path="/powerpoint-uploads/{request_key}", params(("request_key"=Uuid,Path)),responses((status=200,body=PowerPointFile),(status=401,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn receipt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(key): ApiPath<Uuid>,
) -> AppResult<Json<PowerPointFile>> {
    let file = sqlx::query_as("select * from powerpoint_file where actor=$1 and request_key=$2")
        .bind(&user.uid)
        .bind(key)
        .fetch_optional(&s.pool)
        .await?
        .ok_or(AppError::NotFound)?;
    Ok(Json(file))
}

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .merge(super::settings::routes())
        .routes(routes!(resolve, remove))
        .routes(routes!(upload).layer(DefaultBodyLimit::max(
            super::super::config::MAX_FILE_BYTES as usize + 64 * 1024,
        )))
        .routes(routes!(content))
        .routes(routes!(receipt))
}
