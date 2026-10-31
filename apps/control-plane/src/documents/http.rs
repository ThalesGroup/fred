// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Storage, invalid, models::*, unavailable};
use crate::{
    api::AppState,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, Multipart, State},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
};
use std::sync::Arc;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

fn storage(state: &AppState) -> AppResult<&Arc<Storage>> {
    state.content.as_ref().ok_or_else(unavailable)
}
/// Multipart body: exactly one `file` part.
#[allow(dead_code)]
#[derive(utoipa::ToSchema)]
pub(crate) struct FileUpload {
    /// The file; its multipart filename becomes the document name.
    #[schema(value_type=String,format=Binary)]
    file: Vec<u8>,
}

/// Store one file as an immutable original; with `profile`, also request its processing atomically.
/// `Location` names the receipt; replaying a stored `Idempotency-Key` answers 200 with the same receipt.
#[utoipa::path(post,path="/folders/{id}/documents",params(("id"=Uuid,Path,description="Destination folder"),("Idempotency-Key"=Uuid,Header,description="Caller-chosen request UUID; replaying it is safe"),("retry_of"=Option<Uuid>,Query,description="Request key of a failed upload of the same file to the same folder"),("profile"=Option<crate::processing::models::Profile>,Query,description="Processing profile; omit to store only")),request_body(content=FileUpload,content_type="multipart/form-data"),responses(
(status=201,description="Stored",body=UploadReceipt),
(status=200,description="Replay of a stored request key",body=UploadReceipt),
(status=400,description="`invalid_multipart`: not one multipart `file` part",body=crate::error::ErrorBody),
(status=401,description="Missing token, or `token_expired` during the transfer",body=crate::error::ErrorBody),
(status=403,body=crate::error::ErrorBody),
(status=404,body=crate::error::ErrorBody),
(status=408,description="`upload_timeout`: the transfer stalled or exceeded its deadline",body=crate::error::ErrorBody),
(status=409,description="`name_conflict`, `idempotency_conflict`, `upload_failed` (retry with `retry_of`), `invalid_retry`, `upload_expired`, `retry_superseded` (`Location` names the original receipt), or `upload_in_progress` (`Location` and `Retry-After`)",body=crate::error::ErrorBody),
(status=413,description="`file_too_large`: above `max_file_bytes`",body=crate::error::ErrorBody),
(status=422,description="`quota_exceeded`, or an invalid request key, filename or media type",body=crate::error::ErrorBody),
(status=429,description="`transfer_capacity`: all transfer slots are busy; honour `Retry-After`",body=crate::error::ErrorBody),
(status=503,description="`storage_unavailable`, or `processing_unavailable` when a profile is requested",body=crate::error::ErrorBody)
))]
async fn upload(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<UploadQuery>,
    headers: HeaderMap,
    multipart: Result<Multipart, axum::extract::multipart::MultipartRejection>,
) -> AppResult<Response> {
    // Relative to folders/{id}/documents, preserving either mounted API prefix.
    upload_response(
        &s,
        &user,
        Destination::Folder(id),
        query,
        &headers,
        multipart,
        "../../",
    )
    .await
}

/// The upload protocol shared by every destination; `to_root` climbs from the route to the API root.
pub(crate) async fn upload_response(
    s: &AppState,
    user: &crate::auth::CurrentUser,
    destination: Destination,
    query: UploadQuery,
    headers: &HeaderMap,
    multipart: Result<Multipart, axum::extract::multipart::MultipartRejection>,
    to_root: &str,
) -> AppResult<Response> {
    let mut values = headers.get_all("idempotency-key").iter();
    let key = values
        .next()
        .and_then(|h| h.to_str().ok())
        .and_then(|s| Uuid::parse_str(s).ok())
        .ok_or_else(|| invalid("Idempotency-Key must be one UUID"))?;
    if values.next().is_some() {
        return Err(invalid("Idempotency-Key must be one UUID"));
    }
    let outcome = storage(s)?
        .upload(
            user,
            destination,
            key,
            query,
            multipart.map_err(|_| {
                AppError::problem(
                    StatusCode::BAD_REQUEST,
                    "invalid_multipart",
                    "Expected multipart/form-data with one file",
                )
            })?,
            s.processing.as_deref(),
        )
        .await;
    let (mut response, receipt_key) = match outcome {
        Ok((fresh, mut receipt)) => {
            if let Some(id) = receipt.document_id {
                receipt.processing = crate::processing::store::summaries(&s.pool, &[id])
                    .await?
                    .remove(&id);
            }
            (
                (
                    if fresh {
                        StatusCode::CREATED
                    } else {
                        StatusCode::OK
                    },
                    Json(receipt),
                )
                    .into_response(),
                key,
            )
        }
        Err(
            error @ AppError::Problem {
                code: "upload_in_progress",
                ..
            },
        ) => (error.into_response(), key),
        Err(
            error @ AppError::Problem {
                code: "retry_superseded",
                ..
            },
        ) => (error.into_response(), query.retry_of.unwrap_or(key)),
        Err(error) => return Err(error),
    };
    response.headers_mut().insert(
        header::LOCATION,
        format!("{to_root}document-uploads/{receipt_key}")
            .parse()
            .map_err(|_| unavailable())?,
    );
    Ok(response)
}

/// Advisory check before uploading: names already taken in the folder and the current quota.
/// The upload decides; a name free here can still conflict when the file arrives.
#[utoipa::path(post,path="/folders/{id}/documents/preflight",params(("id"=Uuid,Path,description="Destination folder")),request_body=Preflight,responses((status=400,body=crate::error::ErrorBody),(status=200,body=PreflightResult),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=413,description="`file_too_large`: a file is above `max_file_bytes`",body=crate::error::ErrorBody),(status=422,description="Not 1..200 files, or an invalid filename",body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn preflight(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<Preflight>,
) -> AppResult<Json<PreflightResult>> {
    let mut result = storage(&s)?.preflight(&user.uid, id, input).await?;
    result.storage.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    Ok(Json(result))
}

#[utoipa::path(get,path="/spaces/{id}/entries",params(("id"=Uuid,Path),("parent_id"=Option<Uuid>,Query),("search"=Option<String>,Query,description="Literal case-insensitive substring; at most 255 characters."),("order"=Option<EntryOrder>,Query),("offset"=Option<i64>,Query),("limit"=Option<i64>,Query)),responses((status=200,body=Directory),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn entries(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<EntryQuery>,
) -> AppResult<Json<Directory>> {
    let mut directory = Storage::directory(&s.pool, &s.authorization, &user.uid, id, query).await?;
    directory.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    let subjects = directory
        .items
        .iter()
        .filter_map(|entry| match entry {
            Entry::Document(document) => Some(document.created_by.clone()),
            Entry::Folder(_) => None,
        })
        .collect();
    // Display data, read after the SQL transaction: an unavailable directory omits names.
    let names = async {
        crate::api::organization_directory(&s)?
            .display_names(subjects)
            .await
    };
    directory.uploaders = names.await.unwrap_or_else(|_| {
        tracing::warn!("[DOCUMENTS] Uploader names unavailable");
        Default::default()
    });
    Ok(Json(directory))
}

#[utoipa::path(get,path="/spaces/{id}/storage",params(("id"=Uuid,Path)),responses((status=200,body=StorageSummary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn summary(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<StorageSummary>> {
    let mut result = storage(&s)?.summary(&user.uid, id).await?;
    result.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    Ok(Json(result))
}

/// The caller's upload receipts in the space, newest first, each with its latest processing attempt.
/// Superseded receipts are omitted; acknowledged ones too, unless their document is still processing.
#[utoipa::path(get,path="/spaces/{id}/document-uploads",params(("id"=Uuid,Path),("before"=Option<chrono::DateTime<chrono::Utc>>,Query,description="Cursor: `created_at` of the last receipt read; requires `before_key`"),("before_key"=Option<Uuid>,Query,description="Cursor: `request_key` of the last receipt read"),("limit"=Option<i64>,Query,description="1..200, default 50")),responses((status=200,body=Vec<UploadReceipt>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn receipts(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<ReceiptQuery>,
) -> AppResult<Json<Vec<UploadReceipt>>> {
    Ok(Json(storage(&s)?.receipts(&user.uid, id, query).await?))
}

/// One of the caller's upload receipts, with its latest processing attempt; poll it to follow an upload.
#[utoipa::path(get,path="/document-uploads/{id}",params(("id"=Uuid,Path,description="The upload's `Idempotency-Key`")),responses((status=200,body=UploadReceipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn receipt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<UploadReceipt>> {
    Ok(Json(storage(&s)?.receipt(&user.uid, id).await?))
}

/// Dismiss a terminal receipt from the caller's list; repeating it is harmless.
/// The receipt stays readable by key, so replaying its upload remains safe.
#[utoipa::path(put,path="/document-uploads/{id}/acknowledgment",params(("id"=Uuid,Path,description="The upload's `Idempotency-Key`")),responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,description="`upload_in_progress` while pending, `processing_active` while its document is processing",body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn acknowledge(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    storage(&s)?.acknowledge(&user.uid, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Originals are attachments; no conversion or ingestion is triggered by this route.
#[utoipa::path(get,path="/documents/{id}/content",params(("id"=Uuid,Path)),responses((status=200,body=String,content_type="application/octet-stream"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn content(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Response> {
    storage(&s)?.content(&user.uid, id).await
}

#[utoipa::path(delete,path="/documents/{id}",params(("id"=Uuid,Path)),responses((status=202,body=crate::lifecycle::Receipt),(status=200,body=crate::lifecycle::Receipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn delete_document(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<(StatusCode, Json<crate::lifecycle::Receipt>)> {
    let receipt = s
        .lifecycle
        .accept_document(&s.pool, &user.uid, id, None)
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

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(upload).layer(DefaultBodyLimit::max(
            super::config::MAX_FILE_BYTES as usize + 64 * 1024,
        )))
        .routes(routes!(preflight))
        .routes(routes!(entries))
        .routes(routes!(summary))
        .routes(routes!(receipts))
        .routes(routes!(receipt))
        .routes(routes!(acknowledge))
        .routes(routes!(content))
        .routes(routes!(delete_document))
        .route_layer(axum::middleware::from_fn(no_store))
}

pub(crate) async fn no_store(
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> Response {
    let mut response = next.run(request).await;
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        axum::http::HeaderValue::from_static("private, no-store"),
    );
    response
}
