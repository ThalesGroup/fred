// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-owned Wiki of pages and files, with one arbitration for every proposal.
//! File bytes stay in the document catalogue; this domain owns no permission matrix.
mod access;
mod files;
mod format;
pub mod http;
mod index_pg;
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

/// Transaction-bound projection port. The catalogue supplies current facts;
/// this adapter never establishes publication or read authority.
trait WikiIndex: Send + Sync {
    fn project<'a>(
        &'a self,
        conn: &'a mut sqlx::PgConnection,
        space: Uuid,
        page: &'a WikiPageDetail,
    ) -> futures::future::BoxFuture<'a, Result<()>>;
    fn reconcile<'a>(
        &'a self,
        conn: &'a mut sqlx::PgConnection,
    ) -> futures::future::BoxFuture<'a, Result<bool>>;
    fn search<'a>(
        &'a self,
        conn: &'a mut sqlx::PgConnection,
        space: Uuid,
        query: &'a SearchQuery,
    ) -> futures::future::BoxFuture<'a, Result<Vec<SearchCandidate>>>;
    fn excerpts<'a>(
        &'a self,
        conn: &'a mut sqlx::PgConnection,
        space: Uuid,
        query: &'a SearchQuery,
        pages: &'a [(Uuid, Uuid)],
    ) -> futures::future::BoxFuture<'a, Result<Vec<(Uuid, String)>>>;
}

#[derive(Serialize, ToSchema)]
pub struct WikiSearchHit {
    pub page_id: Uuid,
    pub slug: String,
    pub title: String,
    pub page_type: String,
    pub description: Option<String>,
    /// Contextual excerpt, at most 300 characters; PostgreSQL may strip source HTML tags.
    /// Display as text, never HTML or Markdown.
    pub excerpt: String,
}

#[derive(Serialize, ToSchema)]
pub struct WikiSearchResult {
    pub hits: Vec<WikiSearchHit>,
    /// Candidate position; continue only with this value. No snapshot across writes.
    pub next_offset: Option<usize>,
    /// The 200 candidate ceiling was reached; refine the query.
    pub truncated: bool,
}

struct SearchQuery {
    q: String,
    page_type: Option<String>,
    tag: Option<String>,
    limit: usize,
    offset: usize,
}

#[derive(sqlx::FromRow)]
struct SearchCandidate {
    page_id: Uuid,
    revision_id: Uuid,
    page_type: String,
    description: Option<String>,
    candidate_count: i64,
}

/// Startup catch-up is optional for serving HTTP. Retry failures like the lifecycle
/// worker; keep the supervised task alive after completion and cancel on shutdown.
pub async fn startup(pool: &sqlx::PgPool, stopping: impl std::future::Future<Output = ()> + Clone) {
    loop {
        tokio::select! {
            _ = stopping.clone() => return,
            result = reconcile(pool) => match result {
                Ok(()) => break,
                Err(_) => tracing::warn!(
                    error_code = "wiki_index_retry",
                    "Wiki search startup reconciliation failed; retrying in 5 seconds"
                ),
            },
        }
        tokio::select! {
            _ = stopping.clone() => return,
            _ = tokio::time::sleep(std::time::Duration::from_secs(5)) => {},
        }
    }
    stopping.await;
}

/// Initial population and startup catch-up use the same bounded transactions.
/// SKIP LOCKED alone never proves completion: the adapter also probes stale work.
pub async fn reconcile(pool: &sqlx::PgPool) -> Result<()> {
    loop {
        let mut tx = pool.begin().await?;
        sqlx::query("set local statement_timeout = '15s'")
            .execute(&mut *tx)
            .await?;
        let remaining = index_pg::PostgresIndex.reconcile(&mut tx).await?;
        tx.commit().await?;
        if !remaining {
            return Ok(());
        }
        // Release the connection and lock before yielding to writers/other replicas.
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
}

pub const RULES: &str = "__rules__";
const HISTORY_SIZE: usize = 50;

#[derive(Default, Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiPageSummary {
    pub page_id: Uuid,
    pub slug: String,
    pub title: String,
    pub kind: String,
    pub parent_page_id: Option<Uuid>,
    pub position: i32,
    /// A file entry's media type and size; null for pages.
    pub mime: Option<String>,
    pub size: Option<i64>,
    pub updated_at: Option<DateTime<Utc>>,
    pub updated_by: String,
    /// Author of the current revision, distinct from its publisher or last metadata editor.
    pub author_user_id: Option<String>,
    pub agent_instance_id: Option<Uuid>,
    /// The current revision's agent name, as seen in the source conversation.
    pub agent_name: Option<String>,
    /// Display name of author_user_id, resolved after releasing the transaction.
    #[sqlx(default)]
    pub author_name: Option<String>,
    #[sqlx(default)]
    pub updated_by_name: Option<String>,
}

#[derive(Default, Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiPageDetail {
    #[sqlx(flatten)]
    pub page: WikiPageSummary,
    pub content_md: String,
    pub revision_id: Option<Uuid>,
    /// A file entry's bytes are read through `/wiki/revisions/{revision_id}/content`,
    /// its PDF preview, when one was copied with it, through `/preview`.
    pub has_preview: bool,
    /// Native format view for ordinary pages; rules and files have none.
    #[sqlx(skip)]
    pub format: Option<format::WikiFormat>,
    /// Why stored ordinary text has no format view (`path: message`); `content_md`
    /// stays the readable source and the next write must conform.
    #[sqlx(skip)]
    pub format_error: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiPageTree {
    pub pages: Vec<WikiPageSummary>,
}

#[derive(Serialize, ToSchema)]
pub struct WikiAvailability {
    pub enabled: bool,
    /// Human publication authority, independent of the agent writing mode.
    pub can_publish: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiRevisionSummary {
    pub revision_id: Uuid,
    pub status: String,
    pub author_user_id: String,
    pub agent_instance_id: Option<Uuid>,
    pub agent_name: Option<String>,
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

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct WikiProposal {
    pub proposal_id: Uuid,
    /// `page` (new page), `edit` (page text) or `file` (a new file, or a new version
    /// of the file named by `slug`).
    pub kind: String,
    /// `draft` (awaits its author in the conversation), `pending` (awaits an editor)
    /// or `published`. A refused or withdrawn proposal no longer exists.
    pub status: String,
    pub title: String,
    pub slug: Option<String>,
    pub parent_slug: Option<String>,
    pub base_revision_id: Option<Uuid>,
    pub content_md: String,
    pub current_content_md: String,
    /// The entry changed, or a sibling took the name, since the proposal: not acceptable.
    pub outdated: bool,
    pub created_at: DateTime<Utc>,
    pub author_user_id: String,
    pub agent_instance_id: Option<Uuid>,
    pub agent_name: Option<String>,
    /// The frozen copy of a file proposal; null for pages.
    pub mime: Option<String>,
    pub size: Option<i64>,
    pub has_preview: bool,
}

#[derive(Serialize, ToSchema)]
pub struct WikiProposalList {
    pub proposals: Vec<WikiProposal>,
    pub next_cursor: Option<String>,
    pub authors: std::collections::HashMap<String, String>,
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

/// Copy a conversation output, or an authenticated editable-document export.
/// Outputs support a new entry or a new version of `slug` on `base_revision_id`.
/// Exported documents require a saved-content SHA-256 and a destination page.
/// Editors can create a named destination with the first successful copy.
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ProposeWikiFileRequest {
    /// Exactly one source: catalogue document, editable document, or workspace file.
    pub document_id: Option<Uuid>,
    pub writable_document: Option<WritableWikiSource>,
    /// A path in the checked conversation workspace, never a URL.
    pub workspace_file: Option<WorkspaceWikiSource>,
    /// Create or use a page with this name under parent_slug, on confirmation.
    /// Editors only. The page and the first successful file appear together.
    pub destination_title: Option<String>,
    /// The content the person read; without it, the content current at the request.
    pub expected_content_id: Option<Uuid>,
    pub slug: Option<String>,
    pub base_revision_id: Option<Uuid>,
    pub title: Option<String>,
    pub parent_slug: Option<String>,
}

/// The capability owns the source; Control Plane retrieves its authenticated export.
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WritableWikiSource {
    pub document_id: String,
    /// Default Markdown; Word is exported by the document owner.
    pub format: Option<WritableWikiFormat>,
    /// SHA-256 of the saved Markdown at preparation (UTF-8), before export.
    pub sha256: String,
}

#[derive(Deserialize, Serialize, ToSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum WritableWikiFormat {
    Md,
    Docx,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceWikiSource {
    pub path: String,
    /// SHA-256 of the selected bytes, checked against the authenticated source.
    pub sha256: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct WikiConflict {
    pub detail: &'static str,
    pub current_revision_id: Option<Uuid>,
    pub current_content_md: String,
    pub current_format: Option<format::WikiFormat>,
    #[serde(skip)]
    #[schema(ignore)]
    pub(crate) current_kind: String,
}

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    App(#[from] AppError),
    #[error("wiki revision changed")]
    Stale(Box<WikiConflict>),
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
/// A file title is its name with extension; renaming or versioning keeps the extension.
fn same_extension(title: &str, name: &str) -> Result<()> {
    let extension = |value: &str| value.rsplit_once('.').map(|(_, e)| e.to_lowercase());
    if extension(title) != extension(name) {
        return Err(invalid("A Wiki file keeps its file extension."));
    }
    Ok(())
}
