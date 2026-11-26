// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use crate::{
    authorization::RuntimeCaller,
    extract::{ApiJson, ApiPath, ApiQuery},
};
use axum::{Json, extract::State, response::Response};
use utoipa_axum::{router::OpenApiRouter, routes};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Target {
    runtime_id: String,
}
#[derive(Serialize, ToSchema)]
struct WorkerBinding {
    installation_id: Uuid,
    task_queue: String,
}

#[utoipa::path(
    operation_id="capability_preparation_worker",
    get, path="/capability-preparations/worker",
    params(("runtime_id"=String,Query)),
    responses(
        (status=200,body=WorkerBinding),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody)
    )
)]
async fn binding(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiQuery(q): ApiQuery<Target>,
) -> AppResult<Json<WorkerBinding>> {
    worker(&s, &user, &q.runtime_id)?;
    let installation: Uuid =
        sqlx::query_scalar("select namespace from document_storage where singleton")
            .fetch_one(&s.pool)
            .await?;
    Ok(Json(WorkerBinding {
        installation_id: installation,
        task_queue: queue(installation, &q.runtime_id),
    }))
}
#[utoipa::path(
    operation_id="capability_preparation_context",
    get, path="/capability-preparations/{id}",
    params(("id"=Uuid,Path)),
    responses(
        (status=200,body=Work),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody)
    )
)]
async fn context(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Work>> {
    let row = work(&s.pool, id).await?;
    worker(&s, &user, &row.runtime_id)?;
    Ok(Json(row))
}
#[utoipa::path(
    operation_id="capability_preparation_content",
    get, path="/capability-preparations/{id}/content",
    params(("id"=Uuid,Path)),
    responses(
        (status=200,body=String,content_type="application/octet-stream"),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody)
    )
)]
async fn content(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Response> {
    let row = work(&s.pool, id).await?;
    worker(&s, &user, &row.runtime_id)?;
    if row.state != "pending" {
        return Err(AppError::Conflict(
            "Preparation is no longer pending".into(),
        ));
    }
    s.content
        .as_ref()
        .ok_or_else(crate::documents::unavailable)?
        .preparation_file(row.file_id)
        .await
}
#[utoipa::path(
    operation_id="capability_preparation_confirm",
    post, path="/capability-preparations/{id}/confirm",
    params(("id"=Uuid,Path)),
    request_body=ResultConfirmation,
    responses(
        (status=204),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody),
        (status=409,body=crate::error::ErrorBody),
        (status=422,body=crate::error::ErrorBody)
    )
)]
async fn complete(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<ResultConfirmation>,
) -> AppResult<axum::http::StatusCode> {
    let row = work(&s.pool, id).await?;
    worker(&s, &user, &row.runtime_id)?;
    confirm(&s, id, input).await?;
    Ok(axum::http::StatusCode::NO_CONTENT)
}
#[utoipa::path(
    operation_id="capability_preparation_cleanup",
    get, path="/capability-preparations/cleanup",
    params(("runtime_id"=String,Query)),
    responses(
        (status=200,body=Vec<Uuid>),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody)
    )
)]
async fn cleanup(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiQuery(q): ApiQuery<Target>,
) -> AppResult<Json<Vec<Uuid>>> {
    worker(&s, &user, &q.runtime_id)?;
    // A random page: durably blocked erasures cannot starve the others.
    Ok(Json(sqlx::query_scalar("select id from capability_preparation where runtime_id=$1 and state='obsolete' and cleaned_at is null order by random() limit 20").bind(q.runtime_id).fetch_all(&s.pool).await?))
}
#[utoipa::path(
    operation_id="capability_preparation_cleaned",
    post, path="/capability-preparations/{id}/cleaned",
    params(("id"=Uuid,Path)),
    responses(
        (status=204),
        (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody)
    )
)]
async fn cleaned(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<axum::http::StatusCode> {
    let row = work(&s.pool, id).await?;
    worker(&s, &user, &row.runtime_id)?;
    sqlx::query("update capability_preparation set cleaned_at=coalesce(cleaned_at,clock_timestamp()) where id=$1 and state='obsolete'").bind(id).execute(&s.pool).await?;
    Ok(axum::http::StatusCode::NO_CONTENT)
}
#[utoipa::path(operation_id="capability_preparation_text_admission",get,path="/capability-preparations/{id}/text-admission",params(("id"=Uuid,Path)),responses((status=200,body=fred_rust_sdk::inference::InferenceAdmission)))]
async fn text_admission(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<fred_rust_sdk::inference::InferenceAdmission>> {
    let row = work(&s.pool, id).await?;
    worker(&s, &user, &row.runtime_id)?;
    if row.state != "pending" || row.capability_id != "word_template" {
        return Err(AppError::Conflict(
            "Preparation does not accept text calls".into(),
        ));
    }
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space: crate::domain::Space = crate::db::space(&mut *tx, row.space_id).await?.into();
    crate::lifecycle::store::require_active(&mut *tx, row.space_id).await?;
    let models =
        crate::model_catalog::instance::resolve_for_space(&mut tx, &space, &serde_json::json!({}))
            .await?;
    let selection =
        crate::model_catalog::instance::decide(&models, None, false, None).map_err(|_| {
            AppError::Conflict("No text model is available for template preparation".into())
        })?;
    let admitted =
        crate::model_catalog::instance::admit(&mut tx, space.organization, selection).await?;
    tx.commit().await?;
    Ok(Json(admitted))
}
pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(binding))
        .routes(routes!(text_admission))
        .routes(routes!(context))
        .routes(routes!(content))
        .routes(routes!(complete))
        .routes(routes!(cleanup))
        .routes(routes!(cleaned))
}
