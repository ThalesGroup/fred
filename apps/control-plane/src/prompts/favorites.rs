// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Caller-owned preferences: read access is sufficient, and no content write or
//! attribution change occurs. The existing space transaction protects revocation.

use axum::{extract::State, http::StatusCode};
use uuid::Uuid;

use crate::{
    api::AppState,
    domain::Permission,
    error::{AppError, AppResult},
    extract::ApiPath,
    onboarding::AdmittedUser,
    spaces,
};

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(
        add_prompt_favorite,
        remove_prompt_favorite
    ))
}

/// Change only the caller's favorite after checking Read permission in the space mutation transaction.
/// This preference grants no access and does not modify the prompt's content or attribution.
async fn set_favorite(
    s: &AppState,
    actor: &str,
    space_id: Uuid,
    prompt_id: Uuid,
    favorite: bool,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, actor, space_id, Permission::Read).await?;
    let exists: bool = sqlx::query_scalar(
        "select exists(select 1 from prompt where space_id=$1 and prompt_id=$2)",
    )
    .bind(space_id)
    .bind(prompt_id)
    .fetch_one(&mut *tx)
    .await?;
    if !exists {
        return Err(AppError::NotFound);
    }
    if favorite {
        sqlx::query(
            "insert into prompt_favorite(user_id,prompt_id) values ($1,$2) on conflict do nothing",
        )
        .bind(actor)
        .bind(prompt_id)
        .execute(&mut *tx)
        .await?;
    } else {
        sqlx::query("delete from prompt_favorite where user_id=$1 and prompt_id=$2")
            .bind(actor)
            .bind(prompt_id)
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    put, path = "/spaces/{space_id}/prompts/{prompt_id}/favorite",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    responses((status = 204, description = "Favorite set for the caller (idempotent)"),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))
)]
async fn add_prompt_favorite(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    set_favorite(&s, &user.uid, space_id, prompt_id, true).await
}

#[utoipa::path(
    delete, path = "/spaces/{space_id}/prompts/{prompt_id}/favorite",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    responses((status = 204, description = "Favorite removed for the caller (idempotent)"),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))
)]
async fn remove_prompt_favorite(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    set_favorite(&s, &user.uid, space_id, prompt_id, false).await
}
