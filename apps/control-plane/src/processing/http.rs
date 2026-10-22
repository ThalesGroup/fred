// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{Processing, models::*, store};
use crate::{
    api::AppState,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
};
use axum::{
    Json,
    extract::{FromRequestParts, State},
    http::{HeaderMap, header, request::Parts},
    response::Response,
};
use std::sync::Arc;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

pub(crate) fn service(s: &AppState) -> AppResult<&Arc<Processing>> {
    s.processing.as_ref().ok_or_else(super::unavailable)
}
pub struct Worker;
impl FromRequestParts<AppState> for Worker {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, s: &AppState) -> AppResult<Self> {
        let processing = service(s)?;
        let token = parts
            .headers
            .get(header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.strip_prefix("Bearer "));
        let user = processing.auth.authenticate(token).await.map_err(|_| {
            AppError::problem(
                axum::http::StatusCode::UNAUTHORIZED,
                "worker_unauthorized",
                "Invalid processing worker identity",
            )
        })?;
        if !user.service_account
            || user.client_id.as_deref() != Some(&processing.config.worker.client_id)
            || user
                .token_issuer
                .as_deref()
                .map(|s| s.trim_end_matches('/'))
                != Some(processing.config.worker.issuer.trim_end_matches('/'))
            || !user
                .token_audiences
                .contains(&processing.config.worker.audience)
        {
            return Err(AppError::Forbidden);
        }
        Ok(Self)
    }
}
fn key(headers: &HeaderMap) -> AppResult<Uuid> {
    let mut h = headers.get_all("idempotency-key").iter();
    let key = h
        .next()
        .and_then(|v| v.to_str().ok())
        .and_then(|v| Uuid::parse_str(v).ok())
        .ok_or_else(invalid)?;
    if h.next().is_some() {
        return Err(invalid());
    }
    Ok(key)
}
#[utoipa::path(post,path="/documents/{id}/processing",params(("id"=Uuid,Path),("Idempotency-Key"=Uuid,Header)),request_body=Start,responses((status=200,body=Summary),(status=409,body=crate::error::ErrorBody),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn start(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    headers: HeaderMap,
    ApiJson(input): ApiJson<Start>,
) -> AppResult<Json<Summary>> {
    Ok(Json(
        service(&s)?
            .start(&user.uid, key(&headers)?, id, input)
            .await?,
    ))
}
#[derive(Default, serde::Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
pub struct History {
    #[param(nullable)]
    pub before: Option<Uuid>,
}
#[utoipa::path(get,path="/documents/{id}/processing",params(("id"=Uuid,Path),History),responses((status=200,body=Vec<Summary>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn history(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<History>,
) -> AppResult<Json<Vec<Summary>>> {
    Ok(Json(service(&s)?.history(&user.uid, id, q.before).await?))
}
#[utoipa::path(get,path="/document-processing/{id}/work",params(("id"=Uuid,Path)),responses((status=200,body=Work),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn work(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Work>> {
    let p = service(&s)?;
    let row = store::row(&p.pool, id).await?;
    if row.installation_id != p.installation {
        return Err(AppError::NotFound);
    }
    Ok(Json(row.work()))
}
#[utoipa::path(post,path="/document-processing/{id}/claim",params(("id"=Uuid,Path)),request_body=Claim,responses((status=200,body=Descriptor),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn claim(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<Claim>,
) -> AppResult<Json<Descriptor>> {
    if id != input.work.processing_id {
        return Err(invalid());
    }
    Ok(Json(service(&s)?.claim(input).await?))
}
#[utoipa::path(post,path="/document-processing/{id}/commit",params(("id"=Uuid,Path)),request_body=Commit,responses((status=200,body=Summary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn commit(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<Commit>,
) -> AppResult<Json<Summary>> {
    if id != input.work.processing_id {
        return Err(invalid());
    }
    Ok(Json(service(&s)?.commit(input).await?))
}
#[utoipa::path(post,path="/document-processing/{id}/abandon",params(("id"=Uuid,Path)),request_body=Failure,responses((status=200,body=Summary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn abandon(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<Failure>,
) -> AppResult<Json<Summary>> {
    if id != input.work.processing_id {
        return Err(invalid());
    }
    Ok(Json(service(&s)?.abandon(input).await?))
}
#[derive(serde::Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
pub struct OriginalQuery {
    pub generation: Uuid,
}
#[utoipa::path(get,path="/document-processing/{id}/original",params(("id"=Uuid,Path),OriginalQuery),responses((status=200,body=String,content_type="application/octet-stream"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn original(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<OriginalQuery>,
) -> AppResult<Response> {
    let p = service(&s)?;
    let r = store::row(&p.pool, id).await?;
    if r.installation_id != p.installation
        || r.summary.status.terminal()
        || r.generations.last().is_none_or(|g| {
            g.id != q.generation || g.expires_at <= chrono::Utc::now() || g.manifest.is_some()
        })
    {
        return Err(super::conflict("stale_generation"));
    }
    p.authorize_actor(&r).await?;
    p.originals
        .stream_original(crate::db::document(&p.pool, r.summary.document_id).await?)
        .await
}
#[utoipa::path(get,path="/documents/{id}/preview",params(("id"=Uuid,Path),super::preview::PreviewQuery),responses((status=200,body=String,content_type="text/plain"),(status=206,body=String,content_type="text/plain"),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=416,body=crate::error::ErrorBody)))]
async fn preview(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<super::preview::PreviewQuery>,
    headers: HeaderMap,
) -> AppResult<Response> {
    super::preview::preview(&s, &user.uid, id, query, headers).await
}
#[utoipa::path(post,path="/document-processing/{id}/vectors",params(("id"=Uuid,Path)),request_body=super::cleanup::VectorPlan,responses((status=200),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn vectors(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<super::cleanup::VectorPlan>,
) -> AppResult<()> {
    if id != input.work.processing_id {
        return Err(invalid());
    }
    service(&s)?.plan_vectors(input).await
}
#[utoipa::path(get,path="/document-processing/cleanup",responses((status=200,body=Vec<super::cleanup::Cleanup>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn cleanup(
    State(s): State<AppState>,
    Worker: Worker,
) -> AppResult<Json<Vec<super::cleanup::Cleanup>>> {
    Ok(Json(service(&s)?.cleanup_candidates().await?))
}
#[utoipa::path(post,path="/document-processing/cleanup",request_body=super::cleanup::Cleaned,responses((status=200),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=400,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn cleaned(
    State(s): State<AppState>,
    Worker: Worker,
    ApiJson(input): ApiJson<super::cleanup::Cleaned>,
) -> AppResult<()> {
    service(&s)?.cleaned(input).await
}
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(vectors))
        .routes(routes!(cleanup, cleaned))
        .routes(routes!(start, history))
        .routes(routes!(work))
        .routes(routes!(claim))
        .routes(routes!(commit))
        .routes(routes!(abandon))
        .routes(routes!(original))
        .routes(routes!(preview))
}
