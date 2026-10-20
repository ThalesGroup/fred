// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Storage, invalid, models::*, unavailable};
use crate::{
    api::AppState,
    error::{AppError, AppResult},
    onboarding::AdmittedUser,
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, FromRequest, FromRequestParts, Multipart, Path, Query, State},
    http::{HeaderMap, StatusCode, header, request::Parts},
    response::{IntoResponse, Response},
};
use serde::de::DeserializeOwned;
use std::sync::Arc;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

fn storage(state: &AppState) -> AppResult<&Arc<Storage>> {
    state.content.as_ref().ok_or_else(unavailable)
}
pub(crate) struct Id(pub Uuid);
impl<S: Send + Sync> FromRequestParts<S> for Id {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> AppResult<Self> {
        Path::<Uuid>::from_request_parts(parts, state)
            .await
            .map(|Path(id)| Self(id))
            .map_err(|_| invalid("Invalid resource identifier"))
    }
}
pub(crate) struct Params<T>(pub T);
impl<T: DeserializeOwned + Send, S: Send + Sync> FromRequestParts<S> for Params<T> {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> AppResult<Self> {
        Query::<T>::from_request_parts(parts, state)
            .await
            .map(|Query(value)| Self(value))
            .map_err(|_| invalid("Invalid query parameters"))
    }
}

struct Input<T>(T);
impl<T, S> FromRequest<S> for Input<T>
where
    Json<T>: FromRequest<S, Rejection = axum::extract::rejection::JsonRejection>,
    S: Send + Sync,
{
    type Rejection = AppError;
    async fn from_request(req: axum::extract::Request, state: &S) -> AppResult<Self> {
        Json::<T>::from_request(req, state)
            .await
            .map(|Json(value)| Self(value))
            .map_err(|error| match error.status() {
                StatusCode::PAYLOAD_TOO_LARGE => AppError::problem(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "request_too_large",
                    "The request body exceeds the limit",
                ),
                StatusCode::UNPROCESSABLE_ENTITY => invalid("Invalid request fields"),
                _ => AppError::problem(
                    StatusCode::BAD_REQUEST,
                    "invalid_json",
                    "Expected a valid JSON request",
                ),
            })
    }
}

#[allow(dead_code)]
#[derive(utoipa::ToSchema)]
struct FileUpload {
    #[schema(value_type=String,format=Binary)]
    file: Vec<u8>,
}

/// Create one immutable original; the request key is scoped to the authenticated actor.
#[utoipa::path(post,path="/folders/{id}/documents",params(("id"=Uuid,Path),("Idempotency-Key"=Uuid,Header,description="Required request UUID"),("retry_of"=Option<Uuid>,Query),("profile"=Option<crate::processing::models::Profile>,Query,description="Omit for upload only")),request_body(content=FileUpload,content_type="multipart/form-data"),responses(
(status=400,body=crate::error::ErrorBody),(status=201,body=UploadReceipt),(status=200,body=UploadReceipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=408,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=413,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)
))]
async fn upload(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
    Params(query): Params<UploadQuery>,
    headers: HeaderMap,
    multipart: Result<Multipart, axum::extract::multipart::MultipartRejection>,
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
    let outcome = storage(&s)?
        .upload(
            &user,
            id,
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
    // Relative to folders/{id}/documents, preserving either mounted API prefix.
    response.headers_mut().insert(
        header::LOCATION,
        format!("../../document-uploads/{receipt_key}")
            .parse()
            .map_err(|_| unavailable())?,
    );
    Ok(response)
}

#[utoipa::path(post,path="/folders/{id}/documents/preflight",params(("id"=Uuid,Path)),request_body=Preflight,responses((status=400,body=crate::error::ErrorBody),(status=200,body=PreflightResult),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=413,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn preflight(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
    Input(input): Input<Preflight>,
) -> AppResult<Json<PreflightResult>> {
    let mut result = storage(&s)?.preflight(&user.uid, id, input).await?;
    result.storage.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    Ok(Json(result))
}

#[utoipa::path(get,path="/spaces/{id}/entries",params(("id"=Uuid,Path),("parent_id"=Option<Uuid>,Query),("search"=Option<String>,Query),("order"=Option<EntryOrder>,Query),("offset"=Option<i64>,Query),("limit"=Option<i64>,Query)),responses((status=200,body=Directory),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn entries(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
    Params(query): Params<EntryQuery>,
) -> AppResult<Json<Directory>> {
    let mut directory = Storage::directory(&s.pool, &s.fga, &user.uid, id, query).await?;
    directory.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    Ok(Json(directory))
}

#[utoipa::path(get,path="/spaces/{id}/storage",params(("id"=Uuid,Path)),responses((status=200,body=StorageSummary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn summary(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
) -> AppResult<Json<StorageSummary>> {
    let mut result = storage(&s)?.summary(&user.uid, id).await?;
    result.processing_enabled = s.processing.as_ref().is_some_and(|p| p.config.enabled);
    Ok(Json(result))
}

#[utoipa::path(get,path="/spaces/{id}/document-uploads",params(("id"=Uuid,Path),("before"=Option<chrono::DateTime<chrono::Utc>>,Query),("before_key"=Option<Uuid>,Query),("limit"=Option<i64>,Query)),responses((status=200,body=Vec<UploadReceipt>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn receipts(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
    Params(query): Params<ReceiptQuery>,
) -> AppResult<Json<Vec<UploadReceipt>>> {
    Ok(Json(storage(&s)?.receipts(&user.uid, id, query).await?))
}

#[utoipa::path(get,path="/document-uploads/{id}",params(("id"=Uuid,Path)),responses((status=200,body=UploadReceipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn receipt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
) -> AppResult<Json<UploadReceipt>> {
    Ok(Json(storage(&s)?.receipt(&user.uid, id).await?))
}

#[utoipa::path(put,path="/document-uploads/{id}/acknowledgment",params(("id"=Uuid,Path)),responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn acknowledge(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
) -> AppResult<StatusCode> {
    storage(&s)?.acknowledge(&user.uid, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Originals are attachments; no conversion or ingestion is triggered by this route.
#[utoipa::path(get,path="/documents/{id}/content",params(("id"=Uuid,Path)),responses((status=200,body=String,content_type="application/octet-stream"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn content(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Id(id): Id,
) -> AppResult<Response> {
    storage(&s)?.content(&user.uid, id).await
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
