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
    extract::{ApiJson, ApiPath, ApiQuery, idempotency_key},
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    response::Response,
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
        .routes(routes!(wiki_revisions))
        .routes(routes!(restore_wiki_revision))
        .routes(routes!(wiki_revision_file))
        .routes(routes!(wiki_proposals))
        .routes(routes!(propose_wiki_page))
        .routes(routes!(propose_wiki_edit))
        .routes(routes!(propose_wiki_file))
        .routes(routes!(wiki_proposal))
        .routes(routes!(withdraw_wiki_proposal))
        .routes(routes!(submit_wiki_proposal))
        .routes(routes!(accept_wiki_proposal))
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

/// Confirmation and arbitration are the person's own decisions, never a workload's (D5, D6).
async fn person(
    s: &AppState,
    user: &CurrentUser,
    q: &Query,
    space: Uuid,
    permission: Permission,
    mutation: bool,
) -> Result<Access> {
    if q.delegation.agent.is_some() {
        return Err(AppError::Forbidden.into());
    }
    open(s, user, q, space, permission, mutation).await
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
    if !delegated {
        name_pages(s, std::slice::from_mut(&mut page.page)).await;
    }
    Json(page)
}

async fn name_pages(s: &AppState, pages: &mut [WikiPageSummary]) {
    let subjects = pages
        .iter()
        .flat_map(|page| {
            std::iter::once(page.updated_by.clone()).chain(page.author_user_id.clone())
        })
        .filter(|id| !id.is_empty())
        .collect();
    let authors = names(s, subjects).await;
    for page in pages {
        page.author_name = page
            .author_user_id
            .as_ref()
            .and_then(|id| authors.get(id))
            .cloned();
        page.updated_by_name = authors.get(&page.updated_by).cloned();
    }
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/availability",operation_id="wiki_availability",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=WikiAvailability)))]
async fn wiki_availability(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiAvailability>> {
    let mut access = access::open(&s, &user, &q, space, Permission::Read, false).await?;
    if let Some(session) = q.session_id {
        access.own_session(session).await?;
    }
    Ok(Json(WikiAvailability {
        enabled: access.enabled,
        can_publish: access.editor,
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
    let mut tree = access.pages().await?;
    access.tx.commit().await?;
    if q.delegation.agent.is_none() {
        name_pages(&s, &mut tree.pages).await;
    }
    Ok(Json(tree))
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
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("space_id"=Uuid,Path),("session_id"=Option<Uuid>,Query,description="The bound conversation of a delegated call")),request_body=ProposeWikiPageRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=201,description="Draft for a delegated call; pending, or accepted for an editor",body=WikiProposal),(status=409,body=crate::error::ErrorBody)))]
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
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("space_id"=Uuid,Path),("session_id"=Option<Uuid>,Query,description="The bound conversation of a delegated call")),request_body=ProposeWikiEditRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=201,description="Draft for a delegated call; pending, or accepted for an editor",body=WikiProposal),(status=409,body=WikiConflict)))]
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

/// A draft for its author's live conversation, a pending proposal for its author and the
/// editors, an accepted one for every reader; refused or withdrawn is 404.
#[utoipa::path(get,path="/spaces/{space_id}/wiki/proposals/{proposal_id}",operation_id="wiki_proposal",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=200,body=WikiProposal)))]
async fn wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiProposal>> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    Ok(Json(access.proposal(id).await?))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/{proposal_id}/submit",operation_id="submit_wiki_proposal",
    params(("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,description="A delegated call",body=crate::error::ErrorBody),(status=404,description="Not the caller's draft in a live conversation",body=crate::error::ErrorBody),(status=200,description="`pending`, or `published` for an editor",body=WikiProposal),(status=409,body=WikiConflict)))]
async fn submit_wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiProposal>> {
    let mut access = person(&s, &user, &q, space, Permission::Read, true).await?;
    let proposal = access.decide(id, true).await?;
    access.tx.commit().await?;
    Ok(Json(proposal))
}

#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/{proposal_id}/accept",operation_id="accept_wiki_proposal",
    params(("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,description="Not an editor, or a delegated call",body=crate::error::ErrorBody),(status=404,description="No pending proposal",body=crate::error::ErrorBody),(status=200,body=WikiProposal),(status=409,description="Outdated proposal or taken sibling name",body=WikiConflict)))]
async fn accept_wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiProposal>> {
    let mut access = person(&s, &user, &q, space, Permission::Write, true).await?;
    let proposal = access.decide(id, false).await?;
    access.tx.commit().await?;
    Ok(Json(proposal))
}

/// The author withdraws a draft or pending proposal; an editor refuses a pending one.
#[utoipa::path(delete,path="/spaces/{space_id}/wiki/proposals/{proposal_id}",operation_id="withdraw_wiki_proposal",
    params(("space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,description="A delegated call",body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=204)))]
async fn withdraw_wiki_proposal(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<StatusCode> {
    let mut access = person(&s, &user, &q, space, Permission::Read, true).await?;
    access.delete_proposal(id).await?;
    access.tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(get,path="/spaces/{space_id}/wiki/proposals",operation_id="wiki_proposals",
    params(("space_id"=Uuid,Path),("cursor"=Option<String>,Query)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,description="Pending proposals: all for an editor, otherwise the caller's",body=WikiProposalList)))]
async fn wiki_proposals(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Json<WikiProposalList>> {
    let mut access = person(&s, &user, &q, space, Permission::Read, false).await?;
    let mut list = access.proposals(q.cursor.as_deref()).await?;
    access.tx.commit().await?;
    let subjects = list
        .proposals
        .iter()
        .map(|p| p.author_user_id.clone())
        .collect();
    list.authors = names(&s, subjects).await;
    Ok(Json(list))
}

/// A person proposes from their own conversation (`session_id`); a delegated turn
/// drafts from its bound one. `Idempotency-Key` makes the copy safe to retry.
#[utoipa::path(post,path="/spaces/{space_id}/wiki/proposals/file",operation_id="propose_wiki_file",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("space_id"=Uuid,Path),("session_id"=Uuid,Query),
        ("Idempotency-Key"=Uuid,Header,description="Caller-chosen request UUID; replaying it is safe")),request_body=ProposeWikiFileRequest,
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
        (status=201,description="Draft for a delegated call; pending, or accepted for an editor",body=WikiProposal),
        (status=200,description="Replay of a stored request key",body=WikiProposal),
        (status=404,description="Not an output of the caller's live conversation",body=crate::error::ErrorBody),
        (status=408,description="`upload_timeout`",body=crate::error::ErrorBody),
        (status=409,description="`content_changed`, `revision_changed`, a taken sibling name, `idempotency_conflict`, `upload_in_progress`, `upload_failed` or `upload_expired`",body=crate::error::ErrorBody),
        (status=413,description="`file_too_large`",body=crate::error::ErrorBody),
        (status=429,description="`transfer_capacity`",body=crate::error::ErrorBody),
        (status=503,description="`storage_unavailable`",body=crate::error::ErrorBody)))]
async fn propose_wiki_file(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Query>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<ProposeWikiFileRequest>,
) -> Result<(StatusCode, Json<WikiProposal>)> {
    let key = idempotency_key(&headers)?;
    let (fresh, proposal) = files::propose(&s, &user, &q, space, key, body, &headers).await?;
    let status = if fresh {
        StatusCode::CREATED
    } else {
        StatusCode::OK
    };
    Ok((status, Json(proposal)))
}

/// The copied file, or the PDF preview copied with it.
#[derive(Clone, Copy, PartialEq, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum WikiFilePart {
    Content,
    Preview,
}

/// Bytes of an accepted file, or of a proposal as `GET /proposals/{id}` shows it.
#[utoipa::path(get,path="/spaces/{space_id}/wiki/revisions/{revision_id}/{part}",operation_id="wiki_revision_file",
    params(("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),("session_id"=Option<Uuid>,Query),("space_id"=Uuid,Path),("revision_id"=Uuid,Path),("part"=inline(WikiFilePart),Path)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=429,description="`transfer_capacity`",body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),
        (status=200,description="File bytes",headers(("X-Content-Id"=Uuid,description="Identity of the returned bytes")))))]
async fn wiki_revision_file(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, id, part)): ApiPath<(Uuid, Uuid, WikiFilePart)>,
    ApiQuery(q): ApiQuery<Query>,
) -> Result<Response> {
    let mut access = open(&s, &user, &q, space, Permission::Read, false).await?;
    let (content, key, name, size, sha256) = access
        .revision_file(id, part == WikiFilePart::Preview)
        .await?;
    access.tx.commit().await?;
    let storage = s
        .content
        .as_ref()
        .ok_or_else(crate::documents::unavailable)?;
    Ok(storage
        .stream_content(content, &key, &name, size, &sha256)
        .await?)
}
