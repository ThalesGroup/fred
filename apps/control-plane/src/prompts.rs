// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped prompt definitions, validation and persistence. HTTP callers enforce authorization;
//! writes retain the shared space mutation transaction until commit.

use crate::{
    domain::{self, SpaceKind},
    error::{AppError, AppResult},
    extract::present,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

mod categories;
mod favorites;
pub mod http;
mod publication;

pub(super) const PAGE_SIZE: usize = 100;

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
    /// Optional category belonging to this same space.
    pub category_id: Option<Uuid>,
    /// Up to 20 nonblank labels, each at most 64 characters. NFC-normalized and deduplicated.
    #[serde(default)]
    #[schema(max_items = 20)]
    pub tags: Vec<String>,
    /// Nonblank text, preserved verbatim. NUL is rejected.
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
    /// Omitted keeps the category; null removes it.
    #[serde(default, deserialize_with = "present")]
    pub category_id: Option<Option<Uuid>>,
    /// Omitted/null keeps tags; [] clears them.
    #[schema(max_items = 20)]
    pub tags: Option<Vec<String>>,
    /// Omitted/null keeps the value; a nonblank string replaces it verbatim.
    pub text: Option<String>,
}

/// The invited editor exception opens only prompt/category reads and publication.
/// It neither grants ordinary space Read/Write nor enables favorites or CRUD.
/// Authorization is admitted before the read, like existing space prompt reads.
pub(super) async fn authorize_read(
    pool: &sqlx::PgPool,
    authorization: &crate::authorization::Authorization,
    actor: &str,
    space_id: Uuid,
) -> AppResult<crate::domain::Space> {
    if crate::authorization::can_publish_prompts(pool, actor, space_id).await? {
        return crate::spaces::load(pool, space_id).await;
    }
    crate::spaces::authorize(
        pool,
        authorization,
        actor,
        space_id,
        crate::domain::Permission::Read,
    )
    .await
}

pub(super) fn require_prompt_space(kind: SpaceKind) -> AppResult<()> {
    if matches!(kind, SpaceKind::Team | SpaceKind::Personal) {
        Ok(())
    } else {
        Err(AppError::BadRequest(
            "prompts require a team or personal space".into(),
        ))
    }
}

pub(super) fn validate_logical_name(name: &str) -> AppResult<()> {
    if !domain::valid_logical_name(name) || name == "skill" {
        return Err(AppError::Unprocessable(
            "logical_name must contain 1..64 lowercase ASCII letters, digits, '_' or '-'; 'skill' is reserved".into(),
        ));
    }
    Ok(())
}

pub(super) fn validate_content(
    display_name: Option<&mut String>,
    description: Option<&str>,
    text: Option<&str>,
    tags: Option<&mut Vec<String>>,
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
    if text.is_some_and(|text| text.trim().is_empty()) {
        return Err(AppError::Unprocessable(
            "prompt text must not be blank".into(),
        ));
    }
    if let Some(tags) = tags {
        if tags.len() > 20 {
            return Err(AppError::Unprocessable(
                "a prompt accepts at most 20 tags".into(),
            ));
        }
        let mut seen = std::collections::BTreeSet::new();
        for tag in tags.iter_mut() {
            *tag = domain::canonical_name(tag, 64).ok_or_else(|| {
                AppError::Unprocessable(
                    "tags must contain 1..64 characters without control characters".into(),
                )
            })?;
        }
        tags.retain(|tag| seen.insert(tag.clone()));
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

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PromptMetadata {
    pub prompt_id: Uuid,
    pub space_id: Uuid,
    pub published: bool,
    /// Immutable space-local identity. The slash command is "/" + logical_name.
    pub logical_name: String,
    pub display_name: String,
    #[schema(required = true)]
    pub description: Option<String>,
    #[schema(required = true)]
    pub category_id: Option<Uuid>,
    pub tags: Vec<String>,
    pub created_at: DateTime<Utc>,
    pub created_by: String,
    pub updated_at: DateTime<Utc>,
    pub updated_by: String,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PromptSummary {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub metadata: PromptMetadata,
    /// First 240 characters, selected in PostgreSQL without fetching the full body.
    #[schema(max_length = 240)]
    pub text_preview: String,
    pub is_favorite: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct Prompt {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub metadata: PromptMetadata,
    /// Current full text, preserved verbatim.
    pub text: String,
    pub is_favorite: bool,
}

/// Uses the existing (space_id, logical_name) unique index, in ASCII order.
/// Fetch one extra metadata row so the HTTP page can report a continuation.
pub(super) async fn list_by_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    after: Option<&str>,
    actor: &str,
) -> sqlx::Result<Vec<PromptSummary>> {
    sqlx::query_as(
        "select prompt_id, space_id, published, logical_name, display_name, description, category_id, tags,
            created_at, created_by, updated_at, updated_by, left(text, 240) as text_preview,
            exists(select 1 from prompt_favorite f where f.prompt_id = prompt.prompt_id and f.user_id = $4) as is_favorite
        from prompt where space_id = $1 and logical_name > coalesce($2, '')
        order by logical_name limit $3",
    )
    .bind(space_id)
    .bind(after)
    .bind((PAGE_SIZE + 1) as i64)
    .bind(actor)
    .fetch_all(ex)
    .await
}

pub(super) async fn get_for_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    prompt_id: Uuid,
    actor: &str,
) -> sqlx::Result<Option<Prompt>> {
    sqlx::query_as("select prompt.*, exists(select 1 from prompt_favorite f where f.prompt_id = prompt.prompt_id and f.user_id = $3) as is_favorite from prompt where space_id = $1 and prompt_id = $2")
        .bind(space_id)
        .bind(prompt_id)
        .bind(actor)
        .fetch_optional(ex)
        .await
}

pub(super) async fn create<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    body: &CreatePromptRequest,
    actor: &str,
) -> sqlx::Result<Prompt> {
    sqlx::query_as(
        "insert into prompt (prompt_id, space_id, logical_name, display_name, description,
            text, created_by, category_id, tags) values ($1, $2, $3, $4, $5, $6, $7, $8, $9) returning *, false as is_favorite",
    )
    .bind(Uuid::new_v4())
    .bind(space_id)
    .bind(&body.logical_name)
    .bind(&body.display_name)
    .bind(&body.description)
    .bind(&body.text)
    .bind(actor)
    .bind(body.category_id)
    .bind(&body.tags)
    .fetch_one(ex)
    .await
}

/// Apply omissions to a row read under the mutation lock before calling this.
/// The database trigger alone owns update timestamps and no-op attribution.
pub(super) async fn update<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    prompt: &Prompt,
    actor: &str,
) -> sqlx::Result<Prompt> {
    sqlx::query_as(
        "update prompt set display_name = $3, description = $4, text = $5, updated_by = $6, category_id = $7, tags = $8
        where space_id = $1 and prompt_id = $2 returning *,
            exists(select 1 from prompt_favorite f where f.prompt_id = prompt.prompt_id and f.user_id = $6) as is_favorite",
    )
    .bind(prompt.metadata.space_id)
    .bind(prompt.metadata.prompt_id)
    .bind(&prompt.metadata.display_name)
    .bind(&prompt.metadata.description)
    .bind(&prompt.text)
    .bind(actor)
    .bind(prompt.metadata.category_id)
    .bind(&prompt.metadata.tags)
    .fetch_one(ex)
    .await
}

pub(super) async fn delete<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    prompt_id: Uuid,
) -> sqlx::Result<bool> {
    Ok(
        sqlx::query("delete from prompt where space_id = $1 and prompt_id = $2")
            .bind(space_id)
            .bind(prompt_id)
            .execute(ex)
            .await?
            .rows_affected()
            == 1,
    )
}
