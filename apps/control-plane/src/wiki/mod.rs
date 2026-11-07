// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-owned editorial history and conversation-private proposals.
//! This domain deliberately owns no files and no second permission matrix.
mod access;
pub mod http;
pub(crate) mod lifecycle;
mod store;

use crate::error::AppError;
use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

pub const RULES: &str = "__rules__";
const HISTORY_SIZE: usize = 50;

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiPageSummary {
    pub page_id: Uuid,
    pub slug: String,
    pub title: String,
    pub kind: String,
    pub parent_page_id: Option<Uuid>,
    pub position: i32,
    pub needs_review: bool,
    pub updated_at: Option<DateTime<Utc>>,
    pub updated_by: String,
}

#[derive(Serialize, ToSchema)]
pub struct WikiPageDetail {
    pub page: WikiPageSummary,
    pub content_md: String,
    pub revision_id: Option<Uuid>,
    pub author_kind: String,
    pub author_name: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiPageTree {
    pub pages: Vec<WikiPageSummary>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiAvailability {
    pub enabled: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiRevisionSummary {
    pub revision_id: Uuid,
    pub status: String,
    pub author_user_id: String,
    pub author_kind: String,
    pub agent_instance_id: Option<Uuid>,
    pub agent_name: Option<String>,
    pub session_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
    pub reviewed_at: Option<DateTime<Utc>>,
    pub reviewed_by: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiRevisionList {
    pub revisions: Vec<WikiRevisionSummary>,
    pub contents: std::collections::BTreeMap<Uuid, String>,
    pub next_cursor: Option<String>,
    pub authors: std::collections::HashMap<String, String>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiProposal {
    pub proposal_id: Uuid,
    pub kind: String,
    pub title: String,
    pub slug: Option<String>,
    pub parent_slug: Option<String>,
    pub content_md: String,
    pub current_content_md: String,
    pub created_at: DateTime<Utc>,
    pub author_user_id: String,
    pub agent_instance_id: Option<Uuid>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateWikiPageRequest {
    pub title: String,
    #[serde(default)]
    pub content_md: String,
    pub parent_page_id: Option<Uuid>,
    #[serde(default)]
    pub position: i32,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateWikiContentRequest {
    pub content_md: String,
    pub base_revision_id: Option<Uuid>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateWikiMetadataRequest {
    pub title: Option<String>,
    pub parent_page_id: Option<Uuid>,
    #[serde(default)]
    pub move_to_root: bool,
    pub position: Option<i32>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WikiReviewRequest {
    pub needs_review: bool,
    pub base_revision_id: Uuid,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ProposeWikiPageRequest {
    pub title: String,
    pub content_md: String,
    pub parent_slug: Option<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ProposeWikiEditRequest {
    pub slug: String,
    pub content_md: String,
    pub base_revision_id: Uuid,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct WikiConflict {
    pub detail: &'static str,
    pub current_revision_id: Option<Uuid>,
    pub current_content_md: String,
}

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    App(#[from] AppError),
    #[error("wiki revision changed")]
    Stale(WikiConflict),
}
impl From<sqlx::Error> for Error {
    fn from(error: sqlx::Error) -> Self {
        Self::App(error.into())
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        match self {
            Self::App(error) => error.into_response(),
            Self::Stale(body) => (StatusCode::CONFLICT, Json(body)).into_response(),
        }
    }
}
type Result<T> = std::result::Result<T, Error>;
fn invalid(message: &str) -> Error {
    AppError::Unprocessable(message.into()).into()
}

fn content(text: &str, rules: bool) -> Result<()> {
    let max = if rules { 4_000 } else { 100_000 };
    if text.contains('\0') || text.chars().count() > max {
        return Err(invalid("Wiki text is too long or contains NUL characters."));
    }
    Ok(())
}
fn title(value: &str) -> Result<String> {
    crate::domain::canonical_name(value, 300)
        .ok_or_else(|| invalid("A title must contain 1..300 characters without controls."))
}
