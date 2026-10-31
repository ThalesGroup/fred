// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One prompt catalog for management, duplication, draft insertion and slash commands.
//! Consumers must follow next_cursor until null before treating a catalog as complete.
//! Pages are current reads, not a snapshot: refresh from the start to see new names
//! inserted before the cursor. Read the full definition before inserting/sending text.

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    api::AppState,
    db,
    domain::{self, Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery, present},
    onboarding::AdmittedUser,
    spaces,
};

use super::{PAGE_SIZE, Prompt, PromptSummary};

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreatePromptRequest {
    /// Immutable; "skill" is reserved. Invalid names are rejected, never normalized.
    #[schema(min_length = 1, max_length = 64, pattern = "^[a-z0-9_-]{1,64}$")]
    pub logical_name: String,
    /// NFC-normalized and trimmed, nonblank, without control characters.
    #[schema(min_length = 1, max_length = 255)]
    pub display_name: String,
    /// Omitted/null means no description. NUL characters are rejected.
    #[schema(max_length = 500)]
    pub description: Option<String>,
    /// Preserved verbatim, including whitespace and empty strings. NUL is rejected.
    pub text: String,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdatePromptRequest {
    /// Omitted/null keeps the value. Supplied strings follow creation's label rules.
    #[schema(min_length = 1, max_length = 255)]
    pub display_name: Option<String>,
    /// Omitted keeps the value; null clears it; a string replaces it (including "").
    #[serde(default, deserialize_with = "present")]
    #[schema(max_length = 500)]
    pub description: Option<Option<String>>,
    /// Omitted/null keeps the value; a string replaces it verbatim (including "").
    pub text: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PromptQuery {
    after: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct PromptPage {
    /// At most 100 entries, ordered by immutable logical_name in ASCII order.
    #[schema(max_items = 100)]
    pub items: Vec<PromptSummary>,
    /// Pass as `after` until null, including for search, pickers and command menus.
    /// Pages are not a snapshot; restart to include concurrent inserts before the cursor.
    #[schema(required = true)]
    pub next_cursor: Option<String>,
}

fn require_prompt_space(kind: SpaceKind) -> AppResult<()> {
    if matches!(kind, SpaceKind::Team | SpaceKind::Personal) {
        Ok(())
    } else {
        Err(AppError::BadRequest(
            "prompts require a team or personal space".into(),
        ))
    }
}

fn validate_logical_name(name: &str) -> AppResult<()> {
    if !(1..=64).contains(&name.len())
        || name == "skill"
        || !name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
    {
        return Err(AppError::Unprocessable(
            "logical_name must contain 1..64 lowercase ASCII letters, digits, '_' or '-'; 'skill' is reserved".into(),
        ));
    }
    Ok(())
}

fn validate_content(
    display_name: Option<&mut String>,
    description: Option<&str>,
    text: Option<&str>,
) -> AppResult<()> {
    if let Some(name) = display_name {
        *name = domain::canonical_name(name, 255).ok_or_else(|| {
            AppError::Unprocessable(
                "display_name must contain 1..255 characters without control characters".into(),
            )
        })?;
    }
    if description.is_some_and(|s| s.chars().count() > 500) {
        return Err(AppError::Unprocessable(
            "description must contain at most 500 characters".into(),
        ));
    }
    if [description, text]
        .into_iter()
        .flatten()
        .any(|s| s.contains('\0'))
    {
        return Err(AppError::Unprocessable(
            "description and text must not contain NUL characters".into(),
        ));
    }
    Ok(())
}

fn write_error(error: sqlx::Error) -> AppError {
    if error.as_database_error().is_some_and(|db| {
        db.is_unique_violation() && db.constraint() == Some("prompt_space_logical_name_key")
    }) {
        AppError::problem(
            StatusCode::CONFLICT,
            "prompt_name_conflict",
            "A prompt with this logical name already exists in this space.",
        )
    } else {
        error.into()
    }
}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(list_prompts, create_prompt))
        .routes(utoipa_axum::routes!(
            get_prompt,
            update_prompt,
            delete_prompt
        ))
}

/// List metadata for management and chat. Follow next_cursor until null to load
/// the complete catalog. Fetch a definition to obtain current, untruncated text.
#[utoipa::path(
    get, path = "/spaces/{space_id}/prompts",
    params(
        ("space_id" = Uuid, Path),
        ("after" = Option<String>, Query, description = "Exclusive logical_name cursor from next_cursor. Omit for the first page; at most 100 entries per page.")
    ),
    responses(
        (status = 200, body = PromptPage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn list_prompts(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<PromptQuery>,
) -> AppResult<Json<PromptPage>> {
    let space = spaces::authorize(
        &s.pool,
        &s.authorization,
        &user.uid,
        space_id,
        Permission::Read,
    )
    .await?;
    require_prompt_space(space.kind)?;
    if let Some(after) = &query.after {
        validate_logical_name(after)?;
    }
    let mut items = super::list_by_space(&s.pool, space_id, query.after.as_deref()).await?;
    let next_cursor =
        (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].metadata.logical_name.clone());
    items.truncate(PAGE_SIZE);
    Ok(Json(PromptPage { items, next_cursor }))
}

/// Read the current definition for editing, duplication or chat insertion/sending.
#[utoipa::path(
    get, path = "/spaces/{space_id}/prompts/{prompt_id}",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    responses(
        (status = 200, body = Prompt),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn get_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<Prompt>> {
    let space = spaces::authorize(
        &s.pool,
        &s.authorization,
        &user.uid,
        space_id,
        Permission::Read,
    )
    .await?;
    require_prompt_space(space.kind)?;
    Ok(Json(
        super::get_for_space(&s.pool, space_id, prompt_id)
            .await?
            .ok_or(AppError::NotFound)?,
    ))
}

/// Create a prompt, or duplicate one by supplying a new logical_name and copied content.
#[utoipa::path(
    post, path = "/spaces/{space_id}/prompts",
    params(("space_id" = Uuid, Path)),
    request_body = CreatePromptRequest,
    responses(
        (status = 201, body = Prompt),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, description = "prompt_name_conflict on a duplicate logical_name; space lifecycle conflicts retain their shared codes", body = crate::error::ErrorBody),
        (status = 413, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn create_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiJson(mut body): ApiJson<CreatePromptRequest>,
) -> AppResult<(StatusCode, Json<Prompt>)> {
    validate_logical_name(&body.logical_name)?;
    validate_content(
        Some(&mut body.display_name),
        body.description.as_deref(),
        Some(&body.text),
    )?;
    let mut tx = spaces::authorized_write(&s.pool, &user.uid, space_id).await?;
    require_prompt_space(db::space(&mut *tx, space_id).await?.kind)?;
    let prompt = super::create(
        &mut *tx,
        space_id,
        &body.logical_name,
        &body.display_name,
        body.description.as_deref(),
        &body.text,
        &user.uid,
    )
    .await
    .map_err(write_error)?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, Json(prompt)))
}

/// Edit only display_name, description and text. Identity, placement, authorship
/// and unknown fields are rejected. An empty patch preserves update attribution.
#[utoipa::path(
    patch, path = "/spaces/{space_id}/prompts/{prompt_id}",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    request_body = UpdatePromptRequest,
    responses(
        (status = 200, body = Prompt),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 413, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn update_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(mut body): ApiJson<UpdatePromptRequest>,
) -> AppResult<Json<Prompt>> {
    validate_content(
        body.display_name.as_mut(),
        body.description.as_ref().and_then(|value| value.as_deref()),
        body.text.as_deref(),
    )?;
    let mut tx = spaces::authorized_write(&s.pool, &user.uid, space_id).await?;
    require_prompt_space(db::space(&mut *tx, space_id).await?.kind)?;
    // Read after acquiring the shared mutation lock: independent field edits compose.
    let mut current = super::get_for_space(&mut *tx, space_id, prompt_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if let Some(name) = body.display_name {
        current.metadata.display_name = name;
    }
    if let Some(description) = body.description {
        current.metadata.description = description;
    }
    if let Some(text) = body.text {
        current.text = text;
    }
    let prompt = super::update(&mut *tx, &current, &user.uid).await?;
    tx.commit().await?;
    Ok(Json(prompt))
}

#[utoipa::path(
    delete, path = "/spaces/{space_id}/prompts/{prompt_id}",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    responses(
        (status = 204, description = "Prompt deleted"),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn delete_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    let mut tx = spaces::authorized_write(&s.pool, &user.uid, space_id).await?;
    require_prompt_space(db::space(&mut *tx, space_id).await?.kind)?;
    if !super::delete(&mut *tx, space_id, prompt_id).await? {
        return Err(AppError::NotFound);
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
