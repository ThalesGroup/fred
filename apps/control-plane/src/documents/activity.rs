// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Read-only activity projection. The existing upload, processing and deletion
//! owners retain their writes, retention and lifecycle; there is no task store.
use crate::{
    api::AppState,
    authorization,
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
};
use axum::{Json, extract::State};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

macro_rules! activity_enum {
    ($name:ident { $($variant:ident),+ }) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema)]
        #[serde(rename_all = "snake_case")]
        #[sqlx(type_name = "text", rename_all = "snake_case")]
        pub enum $name { $($variant),+ }
    };
}
activity_enum!(ActivityKind {
    Upload,
    Processing,
    DocumentDeletion,
    FolderDeletion
});
activity_enum!(ActivityStatus {
    Pending,
    Running,
    Succeeded,
    Failed,
    Retrying,
    Blocked
});

#[derive(Debug, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct DocumentActivity {
    pub id: Uuid,
    pub kind: ActivityKind,
    pub status: ActivityStatus,
    pub target_id: Option<Uuid>,
    /// Current name where retained; deletion receipts deliberately retain only identity.
    pub name: Option<String>,
    pub stage: Option<String>,
    pub profile: Option<String>,
    pub error_code: Option<String>,
    pub created_at: DateTime<Utc>,
    pub due_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub retry_of: Option<Uuid>,
}

#[derive(Default, Deserialize, utoipa::IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct ActivityQuery {
    pub kind: Option<ActivityKind>,
    pub status: Option<ActivityStatus>,
    /// Opaque keyset cursor, never an offset. Keep `until` and filters when paging.
    pub before: Option<String>,
    /// Fixed upper creation bound. Polling updates outcomes without new rows pushing
    /// a terminal outcome off the page. Omit to start a new view including newer work.
    pub until: Option<DateTime<Utc>>,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct DocumentActivityPage {
    pub items: Vec<DocumentActivity>,
    pub next_cursor: Option<String>,
    pub until: DateTime<Utc>,
}

type Cursor = (DateTime<Utc>, Uuid, ActivityKind);
fn invalid_cursor() -> AppError {
    AppError::problem(
        axum::http::StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_activity_cursor",
        "Invalid activity cursor",
    )
}
fn cursor(value: &str) -> AppResult<Cursor> {
    if value.len() > 512 {
        return Err(invalid_cursor());
    }
    let bytes = URL_SAFE_NO_PAD
        .decode(value)
        .map_err(|_| invalid_cursor())?;
    serde_json::from_slice(&bytes).map_err(|_| invalid_cursor())
}

/// Read and authorization share a snapshot; a committed revocation affects the
/// next read. Exact placement excludes ancestors, descendants and private attachments.
pub async fn list(
    pool: &PgPool,
    actor: &str,
    space_id: Uuid,
    query: ActivityQuery,
) -> AppResult<DocumentActivityPage> {
    let before = query.before.as_deref().map(cursor).transpose()?;
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '10s'")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, actor, space_id, Permission::Read).await?;
    if space.kind != SpaceKind::Team {
        return Err(AppError::Forbidden);
    }
    let now: DateTime<Utc> = sqlx::query_scalar("select transaction_timestamp()")
        .fetch_one(&mut *tx)
        .await?;
    let until = query.until.unwrap_or(now).min(now);
    let mut items: Vec<DocumentActivity> = sqlx::query_as(include_str!("activity.sql"))
        .bind(space_id)
        .bind(space.organization)
        .bind(until)
        .bind(query.kind)
        .bind(query.status)
        .bind(before.as_ref().map(|v| v.0))
        .bind(before.as_ref().map(|v| v.1))
        .bind(before.as_ref().map(|v| v.2))
        .fetch_all(&mut *tx)
        .await?;
    let next_cursor = if items.len() > 50 {
        let last = &items[49];
        Some(
            URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&(last.created_at, last.id, last.kind))
                    .map_err(|e| AppError::Internal(e.into()))?,
            ),
        )
    } else {
        None
    };
    items.truncate(50);
    tx.commit().await?;
    Ok(DocumentActivityPage {
        items,
        next_cursor,
        until,
    })
}

/// Retained team drive operations, newest first, 50 per page. Requires Read, not
/// Manage or ReadUsage. No conversation, child-space, worker payload or credentials.
#[utoipa::path(get, path="/spaces/{id}/document-activity", operation_id="team_document_activity",
    params(("id"=Uuid,Path),ActivityQuery), responses(
        (status=200,body=DocumentActivityPage), (status=401,body=crate::error::ErrorBody),
        (status=403,body=crate::error::ErrorBody), (status=404,body=crate::error::ErrorBody),
        (status=409,body=crate::error::ErrorBody), (status=422,body=crate::error::ErrorBody),
        (status=503,body=crate::error::ErrorBody))) ]
async fn team_document_activity(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<ActivityQuery>,
) -> AppResult<Json<DocumentActivityPage>> {
    Ok(Json(list(&s.pool, &user.uid, id, query).await?))
}
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(team_document_activity))
}
