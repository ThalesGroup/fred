// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped prompt persistence. HTTP callers enforce authorization and validation;
//! writes retain the shared space mutation transaction until commit.

use chrono::{DateTime, Utc};
use serde::Serialize;
use utoipa::ToSchema;
use uuid::Uuid;

pub mod http;

pub(super) const PAGE_SIZE: usize = 100;

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PromptMetadata {
    pub prompt_id: Uuid,
    pub space_id: Uuid,
    /// Immutable space-local identity. The slash command is "/" + logical_name.
    pub logical_name: String,
    pub display_name: String,
    #[schema(required = true)]
    pub description: Option<String>,
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
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct Prompt {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub metadata: PromptMetadata,
    /// Current full text, preserved verbatim.
    pub text: String,
}

/// Uses the existing (space_id, logical_name) unique index, in ASCII order.
/// Fetch one extra metadata row so the HTTP page can report a continuation.
pub(super) async fn list_by_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    after: Option<&str>,
) -> sqlx::Result<Vec<PromptSummary>> {
    sqlx::query_as(
        "select prompt_id, space_id, logical_name, display_name, description,
            created_at, created_by, updated_at, updated_by, left(text, 240) as text_preview
        from prompt where space_id = $1 and logical_name > coalesce($2, '')
        order by logical_name limit $3",
    )
    .bind(space_id)
    .bind(after)
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(ex)
    .await
}

pub(super) async fn get_for_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    prompt_id: Uuid,
) -> sqlx::Result<Option<Prompt>> {
    sqlx::query_as("select * from prompt where space_id = $1 and prompt_id = $2")
        .bind(space_id)
        .bind(prompt_id)
        .fetch_optional(ex)
        .await
}

pub(super) async fn create<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    logical_name: &str,
    display_name: &str,
    description: Option<&str>,
    text: &str,
    actor: &str,
) -> sqlx::Result<Prompt> {
    sqlx::query_as(
        "insert into prompt (prompt_id, space_id, logical_name, display_name, description,
            text, created_by) values ($1, $2, $3, $4, $5, $6, $7) returning *",
    )
    .bind(Uuid::new_v4())
    .bind(space_id)
    .bind(logical_name)
    .bind(display_name)
    .bind(description)
    .bind(text)
    .bind(actor)
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
        "update prompt set display_name = $3, description = $4, text = $5, updated_by = $6
        where space_id = $1 and prompt_id = $2 returning *",
    )
    .bind(prompt.metadata.space_id)
    .bind(prompt.metadata.prompt_id)
    .bind(&prompt.metadata.display_name)
    .bind(&prompt.metadata.description)
    .bind(&prompt.text)
    .bind(actor)
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
