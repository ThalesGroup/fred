// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Conversation attachments: ordinary documents of the conversation's space, reachable
//! only by the conversation owner and only through these routes.

use axum::{
    Json,
    extract::{DefaultBodyLimit, Multipart, State, multipart::MultipartRejection},
    http::{HeaderMap, StatusCode},
    response::Response,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

use crate::{
    api::AppState,
    documents::{
        http::{no_store, upload_response},
        models::{Destination, UploadQuery},
    },
    error::AppResult,
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    processing::models::{Profile, Summary},
};

/// No `profile`: an attachment is always processed with `fast`.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AttachmentQuery {
    pub retry_of: Option<Uuid>,
}

/// One live attachment of the caller's conversation.
#[derive(Serialize, sqlx::FromRow, ToSchema)]
pub struct Attachment {
    pub document_id: Uuid,
    /// NFC-normalized filename, unique within the conversation.
    pub name: String,
    /// MIME type reported by the client; metadata, not verified.
    pub mime: String,
    pub size: i64,
    pub created_at: DateTime<Utc>,
    /// Latest processing attempt.
    #[sqlx(skip)]
    #[schema(required = true)]
    pub processing: Option<Summary>,
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(upload_attachment).layer(DefaultBodyLimit::max(
            crate::documents::config::MAX_FILE_BYTES as usize + 64 * 1024,
        )))
        .routes(routes!(list_attachments))
        .routes(routes!(delete_attachment))
        .route_layer(axum::middleware::from_fn(no_store))
}

/// Attach one file to the caller's conversation and request its `fast` processing atomically.
/// Same protocol as a folder upload; reading the space and owning the conversation suffice.
#[utoipa::path(post, path = "/spaces/{space_id}/sessions/{session_id}/attachments",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path, description = "The caller's conversation"),
        ("Idempotency-Key" = Uuid, Header, description = "Caller-chosen request UUID; replaying it is safe"),
        ("retry_of" = Option<Uuid>, Query, description = "Request key of a failed upload of the same file to the same conversation")),
    request_body(content = crate::documents::http::FileUpload, content_type = "multipart/form-data"),
    responses(
        (status = 201, description = "Stored", body = crate::documents::models::UploadReceipt),
        (status = 200, description = "Replay of a stored request key", body = crate::documents::models::UploadReceipt),
        (status = 400, description = "`invalid_multipart`: not one multipart `file` part", body = crate::error::ErrorBody),
        (status = 401, description = "Missing token, or `token_expired` during the transfer", body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, description = "No such live conversation of the caller", body = crate::error::ErrorBody),
        (status = 408, description = "`upload_timeout`: the transfer stalled or exceeded its deadline", body = crate::error::ErrorBody),
        (status = 409, description = "`name_conflict`, `idempotency_conflict`, `upload_failed` (retry with `retry_of`), `invalid_retry`, `upload_expired`, `retry_superseded` (`Location` names the original receipt), or `upload_in_progress` (`Location` and `Retry-After`)", body = crate::error::ErrorBody),
        (status = 413, description = "`file_too_large`: above `max_file_bytes`", body = crate::error::ErrorBody),
        (status = 422, description = "`quota_exceeded`, or an invalid request key, filename or media type", body = crate::error::ErrorBody),
        (status = 429, description = "`transfer_capacity`: all transfer slots are busy; honour `Retry-After`", body = crate::error::ErrorBody),
        (status = 503, description = "`storage_unavailable` or `processing_unavailable`", body = crate::error::ErrorBody)))]
async fn upload_attachment(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<AttachmentQuery>,
    headers: HeaderMap,
    multipart: Result<Multipart, MultipartRejection>,
) -> AppResult<Response> {
    let choices = UploadQuery {
        retry_of: query.retry_of,
        profile: Some(Profile::Fast),
    };
    // Relative to spaces/{space_id}/sessions/{session_id}/attachments.
    upload_response(
        &s,
        &user,
        Destination::Conversation {
            space_id,
            session_id,
        },
        choices,
        &headers,
        multipart,
        "../../../../",
    )
    .await
}

/// The live attachments of the caller's conversation, oldest first, with their latest processing.
#[utoipa::path(get, path = "/spaces/{space_id}/sessions/{session_id}/attachments",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path)),
    responses((status = 200, body = [Attachment]),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody)))]
async fn list_attachments(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<Vec<Attachment>>> {
    super::require_owner(&s.pool, &s.fga, &user.uid, space_id, session_id).await?;
    let mut attachments: Vec<Attachment> = sqlx::query_as(
        "select id as document_id, name, mime, size, created_at from document
         where session_id = $1 and space_id = $2 and deletion_id is null order by created_at, id",
    )
    .bind(session_id)
    .bind(space_id)
    .fetch_all(&s.pool)
    .await?;
    let ids: Vec<Uuid> = attachments.iter().map(|a| a.document_id).collect();
    let mut summaries = crate::processing::store::summaries(&s.pool, &ids).await?;
    for attachment in &mut attachments {
        attachment.processing = summaries.remove(&attachment.document_id);
    }
    Ok(Json(attachments))
}

/// Delete one attachment of the caller's conversation, as `DELETE /documents/{id}` does.
#[utoipa::path(delete, path = "/spaces/{space_id}/sessions/{session_id}/attachments/{document_id}",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path), ("document_id" = Uuid, Path)),
    responses((status = 202, body = crate::lifecycle::Receipt), (status = 200, body = crate::lifecycle::Receipt),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, description = "`processing_active` while the attachment is processing", body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody)))]
async fn delete_attachment(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id, document_id)): ApiPath<(Uuid, Uuid, Uuid)>,
) -> AppResult<(StatusCode, Json<crate::lifecycle::Receipt>)> {
    let receipt = s
        .lifecycle
        .accept_document(
            &s.pool,
            &s.fga,
            &user.uid,
            document_id,
            Some((space_id, session_id)),
        )
        .await?;
    Ok((
        if receipt.status == crate::lifecycle::Status::Completed {
            StatusCode::OK
        } else {
            StatusCode::ACCEPTED
        },
        Json(receipt),
    ))
}
