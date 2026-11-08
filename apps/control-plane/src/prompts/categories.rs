// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Prompt-local taxonomy. Uses the same authorization and mutation transaction
//! as prompt definitions; SQL enforces ownership and deletion under concurrency.

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    api::AppState,
    domain,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    spaces,
};

use super::PAGE_SIZE;

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PromptCategory {
    pub id: Uuid,
    pub space_id: Uuid,
    pub name: String,
}

#[derive(Serialize, ToSchema)]
pub struct PromptCategoryPage {
    #[schema(max_items = 100)]
    pub items: Vec<PromptCategory>,
    /// Exclusive UUID cursor. Follow until null before displaying category filters.
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CategoryQuery {
    after: Option<Uuid>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PromptCategoryRequest {
    /// NFC-normalized, trimmed, nonblank, without control characters.
    #[schema(min_length = 1, max_length = 120)]
    pub name: String,
}

impl PromptCategoryRequest {
    fn normalize(&mut self) -> AppResult<()> {
        self.name = domain::canonical_name(&self.name, 120).ok_or_else(|| {
            AppError::Unprocessable(
                "category name must contain 1..120 characters without control characters".into(),
            )
        })?;
        Ok(())
    }
}

pub(super) fn write_error(error: sqlx::Error) -> AppError {
    match error.as_database_error().and_then(|db| db.constraint()) {
        Some("prompt_category_space_name_key") => AppError::problem(
            StatusCode::CONFLICT,
            "prompt_category_name_conflict",
            "A category with this name already exists in this space.",
        ),
        Some("prompt_category_same_space_fkey") => AppError::problem(
            StatusCode::CONFLICT,
            "prompt_category_conflict",
            "The category must belong to this space and cannot be deleted while in use.",
        ),
        _ => error.into(),
    }
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(
            list_prompt_categories,
            create_prompt_category
        ))
        .routes(utoipa_axum::routes!(
            rename_prompt_category,
            delete_prompt_category
        ))
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/prompt-categories",
    params(("space_id" = Uuid, Path), ("after" = Option<Uuid>, Query)),
    responses((status = 200, body = PromptCategoryPage),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))
)]
async fn list_prompt_categories(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<CategoryQuery>,
) -> AppResult<Json<PromptCategoryPage>> {
    crate::authorization::authorize(&s.pool, &user.uid, space_id, Permission::Read).await?;
    let mut items: Vec<PromptCategory> = sqlx::query_as(
        "select id, space_id, name from prompt_category
         where space_id = $1 and id > coalesce($2, '00000000-0000-0000-0000-000000000000'::uuid)
         order by id limit $3",
    )
    .bind(space_id)
    .bind(query.after)
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(&s.pool)
    .await?;
    let next_cursor = (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].id);
    items.truncate(PAGE_SIZE);
    Ok(Json(PromptCategoryPage { items, next_cursor }))
}

#[utoipa::path(
    post, path = "/spaces/{space_id}/prompt-categories",
    params(("space_id" = Uuid, Path)), request_body = PromptCategoryRequest,
    responses((status = 201, body = PromptCategory),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))
)]
async fn create_prompt_category(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiJson(mut body): ApiJson<PromptCategoryRequest>,
) -> AppResult<(StatusCode, Json<PromptCategory>)> {
    body.normalize()?;
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    let category = sqlx::query_as(
        "insert into prompt_category (id, space_id, name) values ($1, $2, $3) returning *",
    )
    .bind(Uuid::new_v4())
    .bind(space_id)
    .bind(body.name)
    .fetch_one(&mut *tx)
    .await
    .map_err(write_error)?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, Json(category)))
}

#[utoipa::path(
    patch, path = "/spaces/{space_id}/prompt-categories/{category_id}",
    params(("space_id" = Uuid, Path), ("category_id" = Uuid, Path)), request_body = PromptCategoryRequest,
    responses((status = 200, body = PromptCategory),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))
)]
async fn rename_prompt_category(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, category_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(mut body): ApiJson<PromptCategoryRequest>,
) -> AppResult<Json<PromptCategory>> {
    body.normalize()?;
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    let category = sqlx::query_as(
        "update prompt_category set name = $3 where space_id = $1 and id = $2 returning *",
    )
    .bind(space_id)
    .bind(category_id)
    .bind(body.name)
    .fetch_optional(&mut *tx)
    .await
    .map_err(write_error)?
    .ok_or(AppError::NotFound)?;
    tx.commit().await?;
    Ok(Json(category))
}

#[utoipa::path(
    delete, path = "/spaces/{space_id}/prompt-categories/{category_id}",
    params(("space_id" = Uuid, Path), ("category_id" = Uuid, Path)),
    responses((status = 204, description = "Unused category deleted"),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))
)]
async fn delete_prompt_category(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, category_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    let deleted = sqlx::query("delete from prompt_category where space_id = $1 and id = $2")
        .bind(space_id)
        .bind(category_id)
        .execute(&mut *tx)
        .await
        .map_err(write_error)?;
    if deleted.rows_affected() == 0 {
        return Err(AppError::NotFound);
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
