// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{
    access::{self, Access, Query},
    *,
};
use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization::RuntimeCaller,
    domain::Permission,
    extract::{ApiJson, ApiPath, ApiQuery},
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, State},
    http::StatusCode,
};
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(wiki_availability))
        .routes(routes!(wiki_pages))
        .routes(routes!(create_wiki_page))
        .routes(routes!(wiki_rules))
        .routes(routes!(write_wiki_rules))
        .routes(routes!(wiki_page))
        .routes(routes!(write_wiki_page))
        .routes(routes!(patch_wiki_page))
        .routes(routes!(delete_wiki_page))
        .routes(routes!(set_wiki_review_mark))
        .routes(routes!(wiki_revisions))
        .routes(routes!(restore_wiki_revision))
        .routes(routes!(propose_wiki_page))
        .routes(routes!(propose_wiki_edit))
        .routes(routes!(wiki_proposal))
        .routes(routes!(publish_wiki_proposal))
        .layer(DefaultBodyLimit::max(1024 * 1024))
        .route_layer(axum::middleware::from_fn(crate::documents::http::no_store))
}

async fn open(
    s: &AppState,
    user: &CurrentUser,
    q: &Query,
    space: Uuid,
    permission: Permission,
    mutation: bool,
) -> Result<Access> {
    let access = access::open(s, user, q, space, permission, mutation).await?;
    access.require_enabled()?;
    Ok(access)
}

async fn names(
    s: &AppState,
    subjects: std::collections::BTreeSet<String>,
) -> std::collections::HashMap<String, String> {
    let result = async {
        crate::api::organization_directory(s)?
            .display_names(subjects)
            .await
    };
    result.await.unwrap_or_else(|_| {
        tracing::warn!("Wiki author names unavailable");
        Default::default()
    })
}

async fn named_page(
    s: &AppState,
    mut page: WikiPageDetail,
    delegated: bool,
) -> Json<WikiPageDetail> {
    // Call only after releasing the transaction: the directory can be remote.
    if !delegated && !page.page.updated_by.is_empty() {
        page.author_name = names(s, [page.page.updated_by.clone()].into())
            .await
            .remove(&page.page.updated_by);
    }
    Json(page)
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/availability",operation_id="wiki_availability",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiAvailability)))]
async fn wiki_availability(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiAvailability>> {
    let access = access::open(&s, &user, &q, space, Permission::Read, false).await?;
    Ok(Json(WikiAvailability {
        enabled: access.enabled,
    }))
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/pages",operation_id="wiki_pages",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageTree)))]
async fn wiki_pages(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiPageTree>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    Ok(Json(access.pages().await?))
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/pages/{page_id}",operation_id="wiki_page",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("page_id"=String,Path,description="Stable page slug")),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail)))]
async fn wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, slug)): ApiPath<(Uuid, String)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    if slug == RULES {
        return Err(AppError::Forbidden.into());
    }
    let page = store::by_slug(&mut access.tx, space, &slug).await?;
    access.tx.commit().await?;
    Ok(named_page(&s, page, q.delegation.agent.is_some()).await)
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/rules",operation_id="wiki_rules",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail)))]
async fn wiki_rules(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    let page = access.rules().await?;
    access.tx.commit().await?;
    Ok(named_page(&s, page, q.delegation.agent.is_some()).await)
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/pages",operation_id="create_wiki_page",
    params(("space_id"=Uuid,Path)),request_body=CreateWikiPageRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=201,body=WikiPageDetail),(status=409,body=crate::error::ErrorBody)))]
async fn create_wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<CreateWikiPageRequest>,
) -> Result<(StatusCode, Json<WikiPageDetail>)> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    let page = access.create(body).await?;
    access.tx.commit().await?;
    Ok((StatusCode::CREATED, Json(page)))
}

#[utoipa::path(put,path="/spaces/{space_id}/wiki/pages/{page_id}/content",operation_id="write_wiki_page",
    params(("space_id"=Uuid,Path),("page_id"=Uuid,Path)),request_body=UpdateWikiContentRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail),(status=409,body=WikiConflict)))]
async fn write_wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<UpdateWikiContentRequest>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    if store::page(&mut access.tx, space, id).await?.page.kind == "rules" {
        return Err(AppError::Forbidden.into());
    }
    let page = access.write(id, body).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}

#[utoipa::path(put,path="/spaces/{space_id}/wiki/rules",operation_id="write_wiki_rules",
    params(("space_id"=Uuid,Path)),request_body=UpdateWikiContentRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail),(status=409,body=WikiConflict)))]
async fn write_wiki_rules(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<UpdateWikiContentRequest>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    let page = access.write_rules(body).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}

#[utoipa::path(patch,path="/spaces/{space_id}/wiki/pages/{page_id}",operation_id="patch_wiki_page",
    params(("space_id"=Uuid,Path),("page_id"=Uuid,Path)),request_body=UpdateWikiMetadataRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageSummary),(status=409,body=crate::error::ErrorBody)))]
async fn patch_wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<UpdateWikiMetadataRequest>,
) -> Result<Json<WikiPageSummary>> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    let page = access.metadata(id, body).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}

#[utoipa::path(delete,path="/spaces/{space_id}/wiki/pages/{page_id}",operation_id="delete_wiki_page",
    params(("space_id"=Uuid,Path),("page_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=204),(status=409,body=crate::error::ErrorBody)))]
async fn delete_wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<StatusCode> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    access.delete(id).await?;
    access.tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/pages/{page_id}/review",operation_id="set_wiki_review_mark",
    params(("space_id"=Uuid,Path),("page_id"=Uuid,Path)),request_body=WikiReviewRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageSummary),(status=409,body=WikiConflict)))]
async fn set_wiki_review_mark(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<WikiReviewRequest>,
) -> Result<Json<WikiPageSummary>> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    let page = access.review(id, body).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/pages/{page_id}/revisions",operation_id="wiki_revisions",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("page_id"=Uuid,Path),("cursor"=Option<String>,Query)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiRevisionList)))]
async fn wiki_revisions(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiRevisionList>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    let mut history = access.history(id, q.cursor.as_deref()).await?;
    access.tx.commit().await?;
    let subjects = history
        .revisions
        .iter()
        .flat_map(|r| [Some(r.author_user_id.clone()), r.reviewed_by.clone()])
        .flatten()
        .collect();
    history.authors = names(&s, subjects).await;
    Ok(Json(history))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore",operation_id="restore_wiki_revision",
    params(("space_id"=Uuid,Path),("page_id"=Uuid,Path),("revision_id"=Uuid,Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail),(status=409,body=WikiConflict)))]
async fn restore_wiki_revision(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id, revision)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Write, true).await?;
    let page = access.restore(id, revision).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/page",operation_id="propose_wiki_page",
    params(("person"=String,Query),("run"=String,Query),("agent"=String,Query),("space_id"=Uuid,Path),("session_id"=Uuid,Query)),request_body=ProposeWikiPageRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=201,body=WikiProposal)))]
async fn propose_wiki_page(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<ProposeWikiPageRequest>,
) -> Result<(StatusCode, Json<WikiProposal>)> {
    let mut access = open(&s, &user, &q, space, Permission::Read, true).await?;
    let proposal = access.propose_page(body).await?;
    access.tx.commit().await?;
    Ok((StatusCode::CREATED, Json(proposal)))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/edit",operation_id="propose_wiki_edit",
    params(("person"=String,Query),("run"=String,Query),("agent"=String,Query),("space_id"=Uuid,Path),("session_id"=Uuid,Query)),request_body=ProposeWikiEditRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=201,body=WikiProposal),(status=409,body=WikiConflict)))]
async fn propose_wiki_edit(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
    ApiJson(body): ApiJson<ProposeWikiEditRequest>,
) -> Result<(StatusCode, Json<WikiProposal>)> {
    let mut access = open(&s, &user, &q, space, Permission::Read, true).await?;
    let proposal = access.propose_edit(body).await?;
    access.tx.commit().await?;
    Ok((StatusCode::CREATED, Json(proposal)))
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/proposals/{proposal_id}",operation_id="wiki_proposal",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiProposal)))]
async fn wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiProposal>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    Ok(Json(access.proposal(id).await?))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/{proposal_id}/publish",operation_id="publish_wiki_proposal",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiPageDetail),(status=409,body=WikiConflict)))]
async fn publish_wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiPageDetail>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, true).await?;
    let page = access.publish(id).await?;
    access.tx.commit().await?;
    Ok(Json(page))
}
